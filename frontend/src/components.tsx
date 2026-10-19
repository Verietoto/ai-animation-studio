import { useEffect, useState } from "react";
import { api, Img, VideoModel } from "./api";

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    fn().then((d) => alive && setData(d)).catch((e: Error) => alive && setError(e.message));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, setData };
}

export function ImagePicker({ images, value, onChange, onUploaded }: {
  images: Img[]; value: string | null; onChange: (id: string) => void; onUploaded: (img: Img) => void;
}) {
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function onFile(file: File | undefined) {
    if (!file) return;
    setBusy(true); setErr(null);
    try { const img = await api.upload(file); onUploaded(img); onChange(img.id); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <div>
      <label className="btn">
        {busy ? "Mengunggah…" : "Unggah gambar"}
        <input type="file" accept="image/*" hidden onChange={(e) => onFile(e.target.files?.[0])} />
      </label>
      {err && <p className="error">{err}</p>}
      <div className="thumbs">
        {images.map((i) => (
          <button key={i.id} className={`thumb ${i.id === value ? "sel" : ""}`} onClick={() => onChange(i.id)}
            title={i.prompt ?? i.kind}>
            <img src={api.imageUrl(i.id)} alt={i.prompt ?? i.kind} />
            <span>{i.kind}</span>
          </button>
        ))}
        {images.length === 0 && <p className="muted">Belum ada gambar.</p>}
      </div>
    </div>
  );
}

export interface VideoParams { duration?: number; resolution?: string; aspect_ratio?: string; generate_audio: boolean }

export function ModelParams({ models, model, setModel, params, setParams }: {
  models: VideoModel[]; model: string; setModel: (m: string) => void;
  params: VideoParams; setParams: (p: VideoParams) => void;
}) {
  const i2v = models.filter((m) => m.supported_frame_images?.includes("first_frame")); // hanya model image-to-video
  const info = models.find((m) => m.id === model);
  const select = (label: string, key: "duration" | "resolution" | "aspect_ratio", opts?: (string | number)[]) =>
    opts && opts.length > 0 ? (
      <label>{label}
        <select value={String(params[key] ?? "")}
          onChange={(e) => setParams({ ...params, [key]: key === "duration" ? Number(e.target.value) : e.target.value })}>
          <option value="">(default)</option>
          {opts.map((o) => <option key={String(o)} value={String(o)}>{String(o)}</option>)}
        </select>
      </label>
    ) : null;
  return (
    <div className="row">
      <label>Model
        <select value={model} onChange={(e) => { const next = models.find((m) => m.id === e.target.value); setModel(e.target.value); setParams({ generate_audio: params.generate_audio && next?.generate_audio !== false }); }}>
          <option value="">Pilih model…</option>
          {i2v.map((m) => <option key={m.id} value={m.id}>{m.name ?? m.id}</option>)}
        </select>
      </label>
      {select("Durasi (detik)", "duration", info?.supported_durations)}
      {select("Resolusi", "resolution", info?.supported_resolutions)}
      {select("Rasio", "aspect_ratio", info?.supported_aspect_ratios)}
      <label className="check"><input type="checkbox" checked={params.generate_audio && info?.generate_audio !== false}
        disabled={info?.generate_audio === false} title={info?.generate_audio === false ? "Model ini tidak mendukung suara" : ""}
        onChange={(e) => setParams({ ...params, generate_audio: e.target.checked })} /> Suara</label>
    </div>
  );
}
