// Langkah 3 alur episode: naskah menjadi adegan, manual atau dibantu AI (plan 15).
import { useState } from "react";
import { Bot, Clapperboard, Plus } from "lucide-react";
import { toast } from "sonner";
import { api, EstimateRequest, FilmDetail, JourneyState, SplitScene } from "../../api";
import { EstimateLine, useConfirmedRun, useEstimate } from "../../estimate";
import { EmptyState } from "../../ui";
import { Board } from "../Views";
import { TextModelPicker, useTextModel } from "../../textmodel";

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

export function StepTimeline({ detail, journey, selectedId, locked, reload, onSelect, onAdd, onDelete, onBulkDelete, onReorder, goScript }: {
  detail: FilmDetail; journey: JourneyState; selectedId: string | null; locked: boolean; reload: () => Promise<unknown>;
  onSelect: (id: string) => void; onAdd: () => void; onDelete: (id: string) => void; onBulkDelete?: (ids: string[]) => Promise<unknown>;
  onReorder: (ids: string[]) => void; goScript: () => void;
}) {
  const [draft, setDraft] = useState<{ scenes: SplitScene[]; warnings: string[] } | null>(null);
  const [mode, setMode] = useState<"append" | "replace">("append");
  const [applying, setApplying] = useState(false);
  const p = journey.progress;
  const hasResults = p.keyframe + p.video + p.blockout + p.previs > 0;
  const noScript = !journey.script.trim();
  const locName = (id: string | null) => journey.locations.find((l) => l.id === id)?.name ?? "tanpa latar";
  const charName = (id: string) => journey.characters.find((c) => c.id === id)?.name ?? "?";

  const tm = useTextModel("split");
  const body: EstimateRequest & { v?: string } = { kind: "episode_split", model: tm.model, film_id: detail.id, v: String(journey.script.length) };
  const live = useEstimate(noScript ? null : body);
  const ai = useConfirmedRun(() => body, async (c) => {
    const r = await api.splitScript(detail.id, { model: tm.model, ...c });
    setDraft({ scenes: r.scenes, warnings: r.warnings });
    setMode("append");
    toast.success(`${r.scenes.length} adegan diusulkan${r.cost != null ? ` ($${r.cost.toFixed(4)})` : ""}`);
  });

  const free = async () => {
    try {
      const r = await api.splitFormat(detail.id);
      setDraft({ scenes: r.scenes, warnings: r.warnings });
      setMode("append");
      toast.success(`${r.scenes.length} adegan dibaca dari format (gratis)`);
    } catch (e) { toast.error((e as Error).message); }
  };

  async function apply() {
    if (!draft) return;
    if (mode === "replace" && !window.confirm(`Ganti ${detail.scene_count} adegan yang ada dengan ${draft.scenes.length} adegan dari draf?`)) return;
    setApplying(true);
    try {
      const r = await api.applySplit(detail.id, { scenes: draft.scenes, mode });
      if (r.warnings.length) toast.warning(r.warnings.slice(0, 3).join(" · "));
      toast.success(`${draft.scenes.length} adegan ditambahkan`);
      setDraft(null);
      await reload();
    } catch (e) { toast.error((e as Error).message); }
    finally { setApplying(false); }
  }
  const total = (draft?.scenes ?? []).reduce((s, x) => s + x.planned_seconds, 0);

  return (
    <div className="jr-timeline">
      <div className="jr-card">
        <h3><Bot size={14} /> Pecah naskah jadi adegan</h3>
        {noScript ? (
          <p className="muted">Naskah masih kosong. <button className="linklike" onClick={goScript}>Tulis naskah di langkah 2</button>, atau tambah adegan manual di bawah.</p>
        ) : (<>
          {journey.script_changed && <p className="warn">Naskah berubah sejak adegan terakhir dipecah. Pecah ulang untuk mengikuti perubahan (ditambahkan di akhir, adegan lama tetap).</p>}
          {journey.format.detected && (
            <div className="jr-format">
              <p className={journey.format.errors.length ? "error" : ""}>
                {journey.format.errors.length
                  ? <>Naskah berformat Seedance punya masalah: {journey.format.errors.slice(0, 3).join(" · ")}. Perbaiki di langkah Naskah.</>
                  : <>Naskah sudah berformat Seedance: {journey.format.scenes} adegan, {journey.format.shots} shot. Tidak perlu AI.</>}
              </p>
              <button className="btn primary" disabled={locked || journey.format.errors.length > 0} onClick={() => void free()}>Buat adegan dan beat dari format (gratis)</button>
            </div>
          )}
          <TextModelPicker task="split" value={tm.model} onChange={tm.setModel} hint="Naskah panjang butuh konteks besar; model dengan konteks kecil tidak ditampilkan." />
          <EstimateLine est={live.est} error={live.error} />
          {ai.error && <p className="error">{ai.error}</p>}
          <button className="btn primary" disabled={locked || !!live.error || !live.est || !!live.est.blocked} onClick={() => void ai.start()}>
            <Bot size={14} /> Pecah naskah dengan AI
          </button>
          <p className="muted">Memakai naskah, karakter, dan latar episode. AI tidak menambah karakter/latar baru; hasilnya draf yang kamu periksa dulu.</p>
        </>)}
        {ai.dialog}
        {draft && (
          <div className="jr-draft">
            <h4>Draf: {draft.scenes.length} adegan · {fmt(total)}</h4>
            {draft.warnings.length > 0 && <details><summary className="warn">{draft.warnings.length} peringatan</summary><ul className="muted">{draft.warnings.map((w) => <li key={w}>{w}</li>)}</ul></details>}
            <ol className="jr-draftlist">
              {draft.scenes.map((s, i) => (
                <li key={i}>
                  <strong>{locName(s.location_id)}</strong> · {s.planned_seconds} dtk{s.time_of_day ? ` · ${s.time_of_day}` : ""}
                  {s.cast.map((c) => <div key={c.character_id} className="muted">{charName(c.character_id)}: {c.action}</div>)}
                  {s.camera && <div className="muted">kamera: {s.camera}</div>}
                  {s.beats && <div className="muted">{s.beats.length} shot: {s.beats.map((b) => `${b.size ?? "-"}${b.lens ? ` ${b.lens}mm` : ""}`).join(", ")}</div>}
                </li>
              ))}
            </ol>
            <div className="jr-mode" role="radiogroup" aria-label="Cara menerapkan">
              <label><input type="radio" checked={mode === "append"} onChange={() => setMode("append")} /> Tambahkan di akhir</label>
              <label title={hasResults ? "Ada adegan yang sudah punya keyframe/video/previs" : undefined}>
                <input type="radio" checked={mode === "replace"} disabled={hasResults || detail.scene_count === 0} onChange={() => setMode("replace")} /> Ganti semua adegan
                {hasResults && <span className="muted"> (tidak bisa: sudah ada hasil)</span>}</label>
            </div>
            <div className="actions">
              <button className="btn primary sm" disabled={applying || locked} onClick={() => void apply()}>Terapkan</button>
              <button className="btn ghost sm" onClick={() => setDraft(null)}>Buang draf</button>
            </div>
          </div>
        )}
      </div>

      {detail.scenes.length === 0
        ? <EmptyState icon={<Clapperboard size={36} />} title="Episode ini belum punya adegan" hint="Pecah naskah dengan AI, atau tambah adegan manual.">
            <button className="btn primary" disabled={locked} onClick={onAdd}><Plus size={14} /> Adegan pertama</button>
          </EmptyState>
        : <>
            <p className="muted">{detail.scene_count} adegan · rencana {fmt(detail.planned_seconds)}. Seret untuk mengurutkan; klik adegan untuk mengisi latar, pemeran, dan aksinya di panel kanan.</p>
            <Board scenes={detail.scenes} selectedId={selectedId} locked={locked} onSelect={onSelect} onReorder={onReorder} onAdd={onAdd} onDelete={onDelete} onBulkDelete={onBulkDelete} />
          </>}
    </div>
  );
}
