import { ReactNode, useEffect, useRef, useState } from "react";
import { ImagePlus, Loader2 } from "lucide-react";
import { api, Img, VideoModel } from "./api";
import { ModelPicker } from "./catalog";
import { addPhrase, NEGATIVE_PRESETS } from "./prompts";

/** Model video ini menerima negative prompt? (dari allowed_passthrough_parameters katalog, plan 13) */
export const supportsNegative = (models: VideoModel[], model: string) =>
  !!models.find((m) => m.id === model)?.allowed_passthrough_parameters?.some((p) => p === "negative_prompt" || p === "negativePrompt");

/** Kolom negative prompt; hanya tampil (dan isinya dikosongkan) mengikuti dukungan model. */
export function NegativePrompt({ models, model, value, onChange }: {
  models: VideoModel[]; model: string; value: string; onChange: (v: string) => void;
}) {
  const ok = supportsNegative(models, model);
  useEffect(() => { if (!ok && value) onChange(""); }, [ok, value, onChange]);
  if (!ok) return null;
  return (
    <div className="field">
      <label>Negative prompt (opsional)
        <textarea value={value} onChange={(e) => onChange(e.target.value)} rows={2} maxLength={2000}
          placeholder="Hal yang tidak diinginkan: teks, watermark, blur…" aria-label="Negative prompt" /></label>
      <div className="chips">
        {NEGATIVE_PRESETS.map((p) => (
          <button key={p.label} type="button" className="chip preset" title={p.text} onClick={() => onChange(addPhrase(value, p.text))}>+ {p.label}</button>
        ))}
      </div>
      <p className="muted">Diteruskan ke penyedia model; efeknya tidak bisa dipastikan aplikasi.</p>
    </div>
  );
}

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

const isTyping = (el: EventTarget | null) =>
  el instanceof HTMLElement && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));

/** Unggah gambar dari tombol, drag-drop, atau paste (paste di input teks tidak dicegat). */
export function useUploader(onUploaded: (img: Img) => void, onSelect?: (id: string) => void, paste = true) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const upload = async (file: File | undefined | null) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) return setErr("Hanya file gambar yang bisa diunggah.");
    setBusy(true); setErr(null);
    try { const img = await api.upload(file); onUploaded(img); onSelect?.(img.id); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const ref = useRef(upload); ref.current = upload;
  useEffect(() => {
    if (!paste) return;   // hanya satu strip per halaman yang mendengar paste, supaya tidak terunggah berkali-kali
    const onPaste = (e: ClipboardEvent) => {
      const f = Array.from(e.clipboardData?.files ?? []).find((x) => x.type.startsWith("image/"));
      if (!f) return;
      if (isTyping(e.target) && e.clipboardData?.getData("text/plain")) return;   // paste teks di kolom teks tetap normal; gambar murni (mis. screenshot) tetap diunggah
      e.preventDefault(); ref.current(f);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [paste]);
  return { busy, err, upload };
}

export function Dropzone({ onFile, children, className = "" }: { onFile: (f: File) => void; children: ReactNode; className?: string }) {
  const [over, setOver] = useState(false);
  return (
    <div className={`dropzone ${over ? "over" : ""} ${className}`}
      onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setOver(true); } }}
      onDragLeave={(e) => { if (e.currentTarget === e.target) setOver(false); }}
      onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) onFile(f); }}>
      {children}
    </div>
  );
}

function Thumb({ img, selected, order, onClick }: { img: Img; selected: boolean; order?: number; onClick: () => void }) {
  return (
    <button className={`thumb ${selected ? "sel" : ""}`} onClick={onClick} title={img.prompt ?? img.kind} aria-pressed={selected}>
      <img src={api.imageUrl(img.id)} alt={img.prompt ?? img.kind} loading="lazy" />
      <span className="tag">{img.kind}</span>
      {order != null && <span className="order">{order}</span>}
    </button>
  );
}

function AddButton({ busy, onFile }: { busy: boolean; onFile: (f: File | undefined) => void }) {
  return (
    <label className="add" title="Unggah gambar (atau seret / tempel)">
      {busy ? <Loader2 size={20} className="spin" /> : <ImagePlus size={20} />}
      <input type="file" accept="image/*" hidden onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = ""; }} />
    </label>
  );
}

/** Strip aset horizontal untuk memilih satu gambar. */
export function AssetStrip({ images, value, onChange, onUploaded, paste = true }: {
  images: Img[]; value: string | null; onChange: (id: string) => void; onUploaded: (img: Img) => void; paste?: boolean;
}) {
  const up = useUploader(onUploaded, onChange, paste);
  return (
    <Dropzone onFile={up.upload}>
      <div className="strip" role="group" aria-label="Aset gambar">
        <AddButton busy={up.busy} onFile={up.upload} />
        {images.map((i) => <Thumb key={i.id} img={i} selected={i.id === value} onClick={() => onChange(i.id)} />)}
      </div>
      {images.length === 0 && <p className="muted">Belum ada gambar. Seret, tempel, atau klik + untuk mengunggah.</p>}
      {up.err && <p className="error">{up.err}</p>}
    </Dropzone>
  );
}

/** Strip pilihan banyak (referensi edit foto), urutan klik ditampilkan. */
export function MultiAssetStrip({ images, values, onToggle, max }: {
  images: Img[]; values: string[]; onToggle: (id: string) => void; max: number;
}) {
  return (
    <div className="strip">
      {images.map((i) => {
        const at = values.indexOf(i.id);
        return <Thumb key={i.id} img={i} selected={at >= 0} order={at >= 0 ? at + 1 : undefined}
          onClick={() => (at >= 0 || values.length < max) && onToggle(i.id)} />;
      })}
      {images.length === 0 && <p className="muted">Belum ada gambar lain.</p>}
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
      <label className="field">{label}
        <select value={String(params[key] ?? "")}
          onChange={(e) => setParams({ ...params, [key]: key === "duration" ? Number(e.target.value) : e.target.value })}>
          <option value="">(default)</option>
          {opts.map((o) => <option key={String(o)} value={String(o)}>{String(o)}</option>)}
        </select>
      </label>
    ) : null;
  return (
    <>
      <ModelPicker kind="video" value={model} onChange={(id) => {
        const next = i2v.find((m) => m.id === id);
        setModel(id); setParams({ generate_audio: params.generate_audio && next?.generate_audio !== false });
      }} />
      <div className="row2">
        {select("Durasi (detik)", "duration", info?.supported_durations)}
        {select("Resolusi", "resolution", info?.supported_resolutions)}
        {select("Rasio", "aspect_ratio", info?.supported_aspect_ratios)}
      </div>
      <label className="check"><input type="checkbox" checked={params.generate_audio && info?.generate_audio !== false}
        disabled={info?.generate_audio === false} title={info?.generate_audio === false ? "Model ini tidak mendukung suara" : ""}
        onChange={(e) => setParams({ ...params, generate_audio: e.target.checked })} /> Suara</label>
    </>
  );
}
