import { useCallback, useEffect, useState } from "react";
import { api, Clip, VideoModel } from "../api";
import { ModelParams, useAsync, VideoParams } from "../components";
import { EstimateLine, useConfirmedRun, useEstimate } from "../estimate";

const ACTIVE = ["submitted", "in_progress"];

export default function Library({ refreshImages }: { refreshImages: () => void }) {
  const [clips, setClips] = useState<Clip[]>([]);
  const [error, setError] = useState<string | null>(null);
  const models = useAsync(api.videoModels, []);

  const load = useCallback(() => api.clips().then(setClips).catch((e: Error) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const anyActive = clips.some((c) => ACTIVE.includes(c.status));
  useEffect(() => {
    if (!anyActive) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [anyActive, load]);

  return (
    <section>
      <h2>Library & Extend</h2>
      {error && <p className="error">{error}</p>}
      {clips.length === 0 && <p className="muted">Belum ada klip.</p>}
      <div className="clips">
        {clips.map((c) => <ClipCard key={c.id} clip={c} models={models.data ?? []} onChange={() => { load(); refreshImages(); }} />)}
      </div>
    </section>
  );
}

function ClipCard({ clip, models, onChange }: { clip: Clip; models: VideoModel[]; onChange: () => void }) {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState(clip.model);
  const [params, setParams] = useState<VideoParams>({ generate_audio: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mergedKey, setMergedKey] = useState(clip.has_merged ? 1 : 0);
  const estBody = open && model ? { kind: "video" as const, model, ...params } : null;
  const live = useEstimate(estBody);
  const runner = useConfirmedRun(() => estBody, async (c) => {
    await api.extend(clip.id, { prompt, model, ...params, idempotency_key: crypto.randomUUID(), ...c });
    setOpen(false); setPrompt(""); onChange();
  });

  async function run(fn: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await fn(); onChange(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <article className="clip">
      <div className="status">
        <span className={`pill ${clip.status}`}>{clip.status}</span>
        {clip.chain_depth > 0 && <span className="muted">extend #{clip.chain_depth}</span>}
        {clip.cost != null && <span className="muted">biaya ${clip.cost}{clip.estimated_cost != null && ` (perkiraan $${clip.estimated_cost.toFixed(4)})`}</span>}
        {clip.cost == null && clip.estimated_cost != null && <span className="muted">perkiraan ${clip.estimated_cost.toFixed(4)}</span>}
      </div>
      {clip.has_file ? <video src={api.clipUrl(clip.id)} controls preload="metadata" /> :
        <div className="placeholder">{ACTIVE.includes(clip.status) ? "Sedang diproses…" : "Tidak ada file"}</div>}
      <p className="prompt">{clip.prompt}</p>
      {clip.error && <p className="error">{clip.error}</p>}
      {error && <p className="error">{error}</p>}
      {clip.status === "failed_download" &&
        <button disabled={busy} onClick={() => run(() => api.retryDownload(clip.id))}>Coba unduh lagi (tanpa biaya baru)</button>}
      {clip.status === "completed" && (
        <div className="actions">
          <button onClick={() => setOpen(!open)}>Extend</button>
          {(clip.chain_depth > 0 || clip.has_merged) && (
            <button disabled={busy} onClick={() => run(async () => { await api.merge(clip.id); setMergedKey((k) => k + 1); })}>
              Gabung rantai
            </button>
          )}
        </div>
      )}
      {mergedKey > 0 && <video key={mergedKey} src={`${api.mergedUrl(clip.id)}?v=${mergedKey}`} controls preload="metadata" />}
      {open && (
        <div className="extend">
          <p className="muted">Extend memakai frame terakhir klip ini sebagai frame awal. Sambungan gerak/suara bisa terlihat; rantai panjang menurunkan kualitas.</p>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={2} placeholder="Lanjutkan adegan: …" />
          <ModelParams models={models} model={model} setModel={setModel} params={params} setParams={setParams} />
          <EstimateLine est={live.est} error={live.error} />
          {runner.error && <p className="error">{runner.error}</p>}
          <button className="primary" disabled={busy || !prompt.trim() || !model || !!live.est?.blocked} onClick={runner.start}>
            Buat lanjutan
          </button>
          {runner.dialog}
        </div>
      )}
    </article>
  );
}
