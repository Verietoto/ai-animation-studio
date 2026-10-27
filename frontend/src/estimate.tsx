import { useEffect, useRef, useState } from "react";
import { Coins } from "lucide-react";
import { api, ApiError, Estimate, EstimateRequest } from "./api";
import { Portal } from "./ui";

export const money = (n: number) => (n === 0 ? "$0" : n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(2)}`);

const CONFIDENCE: Record<Estimate["confidence"], string> = {
  exact: "harga pasti dari daftar harga model",
  formula: "dihitung dari rumus token/piksel (+10% margin)",
  history: "berdasarkan biaya nyata job sebelumnya",
  bound: "batas atas konservatif; biasanya jauh lebih murah",
  unknown: "biaya tidak diketahui sebelum selesai",
};

export function rangeText(e: Estimate) {
  if (e.confidence === "unknown") return "tidak diketahui";
  return e.low === e.high ? money(e.high) : `${money(e.low)} sampai ${money(e.high)}`;
}

/** Estimasi langsung saat parameter berubah; respons usang diabaikan. */
export function useEstimate(body: EstimateRequest | null) {
  const [est, setEst] = useState<Estimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  const key = JSON.stringify(body);
  useEffect(() => {
    if (!body || !body.model) { setEst(null); setError(null); return; }
    const mine = ++seq.current;
    const t = setTimeout(() => {
      api.estimate(body)
        .then((e) => { if (mine === seq.current) { setEst(e); setError(null); } })
        .catch((e: Error) => { if (mine === seq.current) { setEst(null); setError(e.message); } });
    }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return { est, error };
}

export function EstimateLine({ est, error }: { est: Estimate | null; error: string | null }) {
  if (error) return <div className="cost"><Coins size={16} /> Perkiraan biaya tidak tersedia: {error}</div>;
  if (!est) return <div className="cost"><Coins size={16} /> Perkiraan biaya muncul setelah model dipilih.</div>;
  return (
    <div className={`cost ${est.blocked ? "blocked" : ""}`}>
      <Coins size={16} /> <strong>{rangeText(est)}</strong>
      <span>{CONFIDENCE[est.confidence]}</span>
      {est.blocked && <strong>ditolak: {est.blocked}</strong>}
    </div>
  );
}

/** Dialog konfirmasi: selalu memakai estimasi segar; server tetap menghitung ulang. */
export function ConfirmDialog({ est, busy, error, onConfirm, onCancel }: {
  est: Estimate; busy: boolean; error: string | null;
  onConfirm: (accept: { confirmed_cost: number | null; accept_unknown_cost: boolean }) => void; onCancel: () => void;
}) {
  const [ack, setAck] = useState(false);
  const unknown = est.confidence === "unknown";
  const cannot = !!est.blocked || (unknown && !ack);
  return (
    <div className="modal" role="dialog" aria-modal="true">
      <div className="modal-box">
        <h3>Konfirmasi biaya</h3>
        <p className="big">{rangeText(est)}</p>
        <p className="muted">{CONFIDENCE[est.confidence]}</p>
        {est.basis.length > 0 && <ul className="muted">{est.basis.map((b, i) => <li key={i}>{b}</li>)}</ul>}
        <p className="muted">
          Terpakai/terpesan hari ini {money(est.committed_today)} dari {money(est.daily_budget)} · sisa {money(est.remaining)}
          {" "}
          · batas per job {money(est.max_per_job)}
        </p>
        {est.blocked && <p className="error">Ditolak: {est.blocked}</p>}
        {unknown && (
          <label className="check"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            Saya mengerti biaya tidak diketahui sebelum job selesai</label>
        )}
        {error && <p className="error">{error}</p>}
        <div className="actions">
          <button className="btn" onClick={onCancel} disabled={busy}>Batal</button>
          <button className="btn primary" disabled={busy || cannot}
            onClick={() => onConfirm({ confirmed_cost: unknown ? null : est.high, accept_unknown_cost: unknown })}>
            {busy ? "Mengirim…" : "Setuju, generate"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Menjalankan alur: ambil estimasi segar -> dialog -> kirim dengan konfirmasi; 409 membuka ulang dialog. */
export function useConfirmedRun(buildEstimate: () => EstimateRequest | null,
                                run: (c: { confirmed_cost: number | null; accept_unknown_cost: boolean }) => Promise<void>) {
  const [pending, setPending] = useState<Estimate | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    const body = buildEstimate();
    if (!body) return;
    setError(null);
    try { setPending(await api.estimate(body)); } catch (e) { setError((e as Error).message); }
  }
  async function confirm(c: { confirmed_cost: number | null; accept_unknown_cost: boolean }) {
    setBusy(true); setError(null);
    try { await run(c); setPending(null); }
    catch (e) {
      if (e instanceof ApiError && e.estimate && (e.status === 409 || e.status === 402)) {
        setPending(e.estimate);
        setError(e.message);
      } else { setError((e as Error).message); }
    } finally { setBusy(false); }
  }
  const dialog = pending && <Portal><ConfirmDialog est={pending} busy={busy} error={error} onConfirm={confirm}
    onCancel={() => { setPending(null); setError(null); }} /></Portal>;
  return { start, dialog, error: pending ? null : error };
}
