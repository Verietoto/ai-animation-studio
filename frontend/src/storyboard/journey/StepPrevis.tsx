// Langkah 4 alur episode (opsional): blockout / previs 3D per adegan sebelum animasi sesungguhnya (plan 15).
import { lazy, Suspense, useState } from "react";
import { Bot, Box, Check, SkipForward } from "lucide-react";
import { toast } from "sonner";
import { api, FilmDetail, JourneyState } from "../../api";
import { useBatch } from "./batch";
import { TextModelPicker, useTextModel } from "../../textmodel";

const Blockout = lazy(() => import("../Blockout"));   // three.js hanya dimuat saat editor dibuka

export function StepPrevis({ detail, journey, locked, reload, onGenerated }: {
  detail: FilmDetail; journey: JourneyState; locked: boolean; reload: () => Promise<unknown>; onGenerated: () => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const tm = useTextModel("scene");
  const pending = detail.scenes.filter((s) => !s.blockout);
  const batch = useBatch("Susun semua adegan dengan AI", "Setiap susunan disimpan langsung ke adegannya; periksa dan ubah di editor 3D sesudahnya.", () => void reload());
  const editScene = detail.scenes.find((s) => s.id === editing) ?? null;

  const composeAll = () => void batch.start(pending.map((s) => ({
    label: `Adegan ${s.number}`,
    estimate: { kind: "scene_blockout" as const, model: tm.model, scene_id: s.id },
    run: async (c) => { const r = await api.sceneBlockout(s.id, { model: tm.model, ...c }); await api.updateScene(s.id, { blockout: r.layout }); },
  })));
  async function toggleSkip() {
    try { await api.updateFilm(detail.id, { previs_skipped: !journey.previs_skipped }); await reload(); }
    catch (e) { toast.error((e as Error).message); }
  }

  return (
    <div className="jr-previs">
      <div className="jr-card">
        <h3><Box size={14} /> Previs 3D (opsional)</h3>
        <p className="muted">Susun manekin, properti, dan kamera bergerak untuk tiap adegan sebelum membuat animasi. Berguna untuk memeriksa komposisi dan gerak lebih dulu; video previs bisa dipakai sebagai referensi gerak di langkah animasi.</p>
        <TextModelPicker task="scene" value={tm.model} onChange={tm.setModel} />
        <div className="actions">
          <button className="btn primary" disabled={locked || batch.busy || pending.length === 0 || detail.scenes.length === 0} onClick={composeAll}>
            <Bot size={14} /> Susun semua dengan AI ({pending.length})
          </button>
          <button className={`btn ${journey.previs_skipped ? "" : "ghost"}`} onClick={() => void toggleSkip()}>
            {journey.previs_skipped ? <><Check size={14} /> Dilewati (batalkan)</> : <><SkipForward size={14} /> Lewati langkah ini</>}
          </button>
        </div>
        {detail.scenes.length === 0 && <p className="warn">Belum ada adegan; buat timeline di langkah 3 dulu.</p>}
      </div>
      <ul className="jr-rows">
        {detail.scenes.map((s) => (
          <li key={s.id} className="jr-row">
            <div className="jr-thumb">{s.blockout_image_id ? <img src={api.imageUrl(s.blockout_image_id)} alt="" loading="lazy" /> : <Box size={20} />}</div>
            <div className="jr-grow">
              <strong>Adegan {s.number}</strong> <span className="muted">{s.location?.name ?? "tanpa latar"} · {s.planned_seconds ?? "?"} dtk</span>
              <div className="muted clamp1">{s.cast.map((c) => `${c.character_name}${c.action ? `: ${c.action}` : ""}`).join(" · ") || "tanpa pemeran"}</div>
              <div className="chips">
                <span className={`chip ${s.blockout ? "" : "meta"}`}>{s.blockout ? "susunan ✓" : "belum disusun"}</span>
                <span className={`chip ${s.previs_ref_id ? "" : "meta"}`}>{s.previs_ref_id ? "previs ✓" : "belum dirender"}</span>
              </div>
            </div>
            <button className="btn sm" disabled={locked || batch.busy} onClick={() => setEditing(s.id)}>{s.blockout ? "Buka editor" : "Susun"}</button>
          </li>
        ))}
      </ul>
      {batch.dialog}
      {editScene && (
        <Suspense fallback={null}>
          <Blockout scene={editScene} aspect={detail.aspect_ratio} onClose={() => setEditing(null)} onSaved={() => { void reload(); onGenerated(); }} />
        </Suspense>
      )}
    </div>
  );
}
