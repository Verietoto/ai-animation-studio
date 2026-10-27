// Aksi massal berbayar (plan 15 fase C): satu konfirmasi total, lalu dijalankan BERURUTAN dari browser, satu permintaan per item.
// Alasan (grill 15): keyframe dibuat sinkron dan lama, jadi tidak boleh satu permintaan server. Server tetap `authorize` tiap job
// (batas per job dan harian); batch berhenti begitu satu item gagal atau jumlah yang berjalan melewati total yang dikonfirmasi.
import { useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, EstimateRequest } from "../../api";
import { money } from "../../estimate";
import { Portal } from "../../ui";

type Confirmation = { confirmed_cost: number | null; accept_unknown_cost: boolean };
export interface BatchItem { label: string; estimate: EstimateRequest; run: (c: Confirmation) => Promise<unknown> }
interface Ready { item: BatchItem; high: number; unknown: boolean }

export function useBatch(title: string, note: string, onFinished: () => void) {
  const [phase, setPhase] = useState<"idle" | "estimating" | "confirm" | "running">("idle");
  const [ready, setReady] = useState<Ready[]>([]);
  const [skipped, setSkipped] = useState<{ label: string; reason: string }[]>([]);
  const [done, setDone] = useState(0);
  const cancel = useRef(false);
  const budget = useRef({ remaining: 0, maxPerJob: 0 });

  async function start(items: BatchItem[]) {
    if (items.length === 0) return void toast("Tidak ada yang perlu dikerjakan");
    setPhase("estimating"); setSkipped([]); setDone(0);
    const ok: Ready[] = [], bad: { label: string; reason: string }[] = [];
    for (const item of items) {
      try {
        const est = await api.estimate(item.estimate);
        budget.current = { remaining: est.remaining, maxPerJob: est.max_per_job };
        if (est.blocked) bad.push({ label: item.label, reason: est.blocked });
        else ok.push({ item, high: est.high, unknown: est.confidence === "unknown" });
      } catch (e) { bad.push({ label: item.label, reason: (e as Error).message }); }
    }
    setReady(ok); setSkipped(bad);
    if (ok.length === 0) { setPhase("idle"); toast.error(`Tidak ada yang bisa dikerjakan: ${bad[0]?.reason ?? ""}`); return; }
    setPhase("confirm");
  }

  const total = ready.reduce((s, r) => s + r.high, 0);
  const overBudget = total > budget.current.remaining;
  const unknown = ready.some((r) => r.unknown);

  async function run() {
    cancel.current = false; setPhase("running"); setDone(0);
    let spent = 0, finished = 0, reason: string | null = null;
    for (const r of ready) {
      if (cancel.current) { reason = "dibatalkan"; break; }
      if (spent + r.high > total + 1e-6) { reason = "estimasi berubah melewati total yang dikonfirmasi"; break; }
      try {
        await r.item.run({ confirmed_cost: r.unknown ? null : r.high, accept_unknown_cost: r.unknown });
        spent += r.high; finished += 1; setDone(finished);
      } catch (e) { reason = `${r.item.label}: ${(e as Error).message}`; break; }
    }
    setPhase("idle"); onFinished();
    if (reason) toast.warning(`${finished} dari ${ready.length} selesai; berhenti: ${reason}`, { duration: 15000 });
    else toast.success(`${finished} item dikerjakan`);
  }

  const dialog = phase === "idle" ? null : (
    <Portal>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-box">
          <h3>{title}</h3>
          {phase === "estimating" && <p className="muted"><Loader2 size={14} className="spin" /> Menghitung biaya…</p>}
          {phase === "confirm" && <>
            <p className="big">{unknown ? "≥ " : ""}{money(total)}</p>
            <p>{ready.length} item, dikerjakan satu per satu. Batas harian tersisa {money(budget.current.remaining)}; batas per item {money(budget.current.maxPerJob)}.</p>
            {overBudget && <p className="error">Total melewati sisa batas harian; item terakhir akan berhenti otomatis.</p>}
            {unknown && <p className="warn">Sebagian biaya tidak diketahui pasti.</p>}
            {note && <p className="muted">{note}</p>}
            <ul className="muted">{ready.slice(0, 6).map((r) => <li key={r.item.label}>{r.item.label} · {money(r.high)}</li>)}{ready.length > 6 && <li>…dan {ready.length - 6} lagi</li>}</ul>
            {skipped.length > 0 && <details><summary className="warn">{skipped.length} dilewati</summary>
              <ul className="muted">{skipped.map((s) => <li key={s.label}>{s.label}: {s.reason}</li>)}</ul></details>}
            <p className="muted">Jangan tutup tab selama berjalan; menutupnya menghentikan sisa item.</p>
            <div className="actions">
              <button className="btn" onClick={() => setPhase("idle")}>Batal</button>
              <button className="btn primary" onClick={() => void run()}>Kerjakan semua</button>
            </div>
          </>}
          {phase === "running" && <>
            <p><Loader2 size={14} className="spin" /> {done} / {ready.length} selesai{ready[done] ? ` · sekarang: ${ready[done].item.label}` : ""}</p>
            <div className="actions"><button className="btn" onClick={() => { cancel.current = true; }}>Hentikan setelah item ini</button></div>
          </>}
        </div>
      </div>
    </Portal>
  );
  return { start, dialog, busy: phase !== "idle" };
}
