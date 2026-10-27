import { useEffect, useRef, useState } from "react";
import { ChevronRight, Clapperboard, Copy, Download, Film, Image as ImageIcon, Layers, Loader2, Trash2, Wand2, X } from "lucide-react";
import { api, Character, Clip, Img, friendlyError } from "./api";
import { ModelParams, NegativePrompt, supportsNegative, useAsync, VideoParams } from "./components";
import { EstimateLine, money, useConfirmedRun, useEstimate } from "./estimate";
import { ACTIVE } from "./queue";
import { Portal } from "./ui";
import { useWorkspaces } from "./workspaces";

export type ItemRef = { type: "image" | "clip"; id: string };

interface Node { ref: ItemRef; label: string; thumb: string }

/** Jejak asal: gambar asli -> edit -> ... -> klip -> extend, dari akar ke item yang dibuka. */
function lineage(start: ItemRef, images: Map<string, Img>, clips: Map<string, Clip>): Node[] {
  const out: Node[] = [];
  let cur: ItemRef | null = start;
  const seen = new Set<string>();
  while (cur && !seen.has(`${cur.type}${cur.id}`) && out.length < 24) {   // seen: jaga dari siklus data
    seen.add(`${cur.type}${cur.id}`);
    if (cur.type === "clip") {
      const c = clips.get(cur.id);
      if (!c) break;
      out.unshift({ ref: cur, label: c.chain_depth > 0 ? `Extend #${c.chain_depth}` : c.kind === "motion" ? "Tiru gerakan" : "Video", thumb: c.source_image_id ? api.imageUrl(c.source_image_id) : "" });
      cur = c.parent_clip_id ? { type: "clip", id: c.parent_clip_id } : c.source_image_id ? { type: "image", id: c.source_image_id } : null;
    } else {
      const i = images.get(cur.id);
      if (!i) break;
      out.unshift({ ref: cur, label: { upload: "Unggahan", edit: "Edit", frame: "Frame", sheet: "Sheet", keyframe: "Keyframe", location: "Latar", anchor: "Anchor", portrait: "Potret" }[i.kind], thumb: api.imageUrl(i.id) });
      cur = i.parent_image_id ? { type: "image", id: i.parent_image_id } : null;
    }
  }
  return out;
}

function useFocusTrap(ref: React.RefObject<HTMLElement>, onClose: () => void) {
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const back = document.activeElement as HTMLElement | null;
    el.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); onClose(); return; }
      if (e.key !== "Tab") return;
      const f = [...el.querySelectorAll<HTMLElement>("button:not(:disabled), a[href], input, select, textarea, [tabindex]:not([tabindex='-1'])")];
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    el.addEventListener("keydown", onKey);
    return () => { el.removeEventListener("keydown", onKey); back?.focus?.(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

function ExtendForm({ clip, onDone }: { clip: Clip; onDone: () => void }) {
  const models = useAsync(api.videoModels, []);
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState(clip.model);
  const [params, setParams] = useState<VideoParams>({ generate_audio: false });
  const [negative, setNegative] = useState("");
  const estBody = model ? { kind: "video" as const, model, ...params } : null;
  const live = useEstimate(estBody);
  const runner = useConfirmedRun(() => estBody, async (c) => {
    await api.extend(clip.id, { prompt, model, ...params,
      negative_prompt: supportsNegative(models.data ?? [], model) ? negative.trim() || undefined : undefined, idempotency_key: crypto.randomUUID(), ...c });
    onDone();
  });
  return (
    <div className="section">
      <h3>Extend</h3>
      <p className="muted">Memakai frame terakhir klip ini sebagai frame awal. Sambungan gerak/suara bisa terlihat; rantai panjang menurunkan kualitas.</p>
      <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={2} placeholder="Lanjutkan adegan: …" aria-label="Prompt lanjutan" />
      <ModelParams models={models.data ?? []} model={model} setModel={setModel} params={params} setParams={setParams} />
      <NegativePrompt models={models.data ?? []} model={model} value={negative} onChange={setNegative} />
      <EstimateLine est={live.est} error={live.error} />
      {runner.error && <p className="error">{runner.error}</p>}
      <button className="btn primary" disabled={!prompt.trim() || !model || !!live.est?.blocked} onClick={runner.start}>Buat lanjutan</button>
      {runner.dialog}
    </div>
  );
}

export function Lightbox({ item, images, clips, characters, onOpen, onClose, onEdit, onToVideo, onAddToFilm, reload }: {
  item: ItemRef; images: Img[]; clips: Clip[]; characters: Character[];
  onOpen: (r: ItemRef) => void; onClose: () => void; onEdit: (id: string) => void; onToVideo: (id: string) => void;
  onAddToFilm: (clipId: string) => void; reload: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, onClose);
  const { askCopy } = useWorkspaces();
  const imgMap = new Map(images.map((i) => [i.id, i]));
  const clipMap = new Map(clips.map((c) => [c.id, c]));
  const img = item.type === "image" ? imgMap.get(item.id) : undefined;
  const clip = item.type === "clip" ? clipMap.get(item.id) : undefined;
  const [extendOpen, setExtendOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mergedKey, setMergedKey] = useState(0);
  const [confirmDel, setConfirmDel] = useState(false);
  useEffect(() => { setExtendOpen(false); setConfirmDel(false); setError(null); setMergedKey(clip?.has_merged ? 1 : 0); }, [item.id, clip?.has_merged]);

  if (!img && !clip) return null;   // item hilang dari daftar (mis. daftar disegarkan): jangan tampilkan kotak kosong
  const [userPrompt, ...roleParts] = (img?.prompt ?? clip?.prompt ?? "").split("\n---\n");   // plan 06: teks user, lalu peran gambar
  const roleText = roleParts.join("\n---\n") || null;
  const trail = lineage(item, imgMap, clipMap);
  const owner = img ? characters.find((c) => c.images.some((x) => x.image_id === img.id)) : undefined;
  const running = clip ? ACTIVE.includes(clip.status) : false;
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError(null);
    try { await fn(); reload(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  let duration: number | undefined;
  try { duration = clip ? (JSON.parse(clip.params) as { duration?: number }).duration : undefined; } catch { /* params bukan JSON */ }

  return (
    <Portal>
      <div className="modal lb" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
        <div className="lightbox" ref={ref} role="dialog" aria-modal="true" tabIndex={-1}
          aria-label={img ? "Detail gambar" : "Detail video"}>
          <div className="lb-stage">
            {img && <img src={api.imageUrl(img.id)} alt={img.prompt ?? img.kind} />}
            {clip && (clip.has_file
              ? <video key={clip.id} src={api.clipUrl(clip.id)} controls autoPlay loop playsInline />
              : <div className="placeholder" style={{ width: "60%" }}>{running ? <><Loader2 className="spin" /> Sedang diproses…</> : "Tidak ada file"}</div>)}
          </div>
          <aside className="lb-side">
            <header className="lb-head">
              <h2>{img ? "Gambar" : "Video"}{owner ? ` · ${owner.name}` : ""}</h2>
              <button className="btn ghost sm" onClick={onClose} aria-label="Tutup"><X size={16} /></button>
            </header>
            {trail.length > 1 && (
              <nav className="trail" aria-label="Asal item">
                {trail.map((n, i) => (
                  <span key={`${n.ref.type}${n.ref.id}`} className="trail-item">
                    {i > 0 && <ChevronRight size={12} />}
                    <button className={`btn sm ${n.ref.id === item.id ? "" : "ghost"}`} onClick={() => onOpen(n.ref)} aria-current={n.ref.id === item.id}>{n.label}</button>
                  </span>
                ))}
              </nav>
            )}
            <dl className="facts">
              {img && <><dt>Ukuran</dt><dd>{img.width}×{img.height}</dd></>}
              {img?.origin_workspace && <><dt>Asal</dt><dd>Disalin dari workspace {img.origin_workspace}</dd></>}
              {(img?.model || clip?.model) && <><dt>Model</dt><dd className="mono">{img?.model ?? clip?.model}</dd></>}
              {clip && <><dt>Status</dt><dd><span className={`pill ${clip.status}`}>{clip.status}</span></dd></>}
              {duration != null && <><dt>Durasi</dt><dd>{duration} detik</dd></>}
              {clip?.negative_prompt && <><dt>Negative prompt</dt><dd>{clip.negative_prompt}</dd></>}
              {clip?.last_image_id && <><dt>Frame akhir</dt><dd>
                <button type="button" className="thumb-btn" aria-label="Buka frame akhir" onClick={() => onOpen({ type: "image", id: clip.last_image_id! })}>
                  <img src={api.imageUrl(clip.last_image_id)} alt="" style={{ width: 56, height: 56, objectFit: "cover", borderRadius: 6 }} /></button></dd></>}
              {(img ?? clip)!.cost != null
                ? <><dt>Biaya</dt><dd className="mono">{money((img ?? clip)!.cost!)}</dd></>
                : (img ?? clip)!.estimated_cost != null && <><dt>Perkiraan</dt><dd className="mono">{money((img ?? clip)!.estimated_cost!)}</dd></>}
            </dl>
            {userPrompt && <p className="lb-prompt">{userPrompt}</p>}
            {roleText && (
              <details><summary className="muted">Instruksi referensi (karakter, pose, ekspresi)</summary>
                <p className="lb-prompt">{roleText}</p></details>
            )}
            {clip?.error && <p className="error">{friendlyError(clip.error)}</p>}
            {error && <p className="error">{error}</p>}
            <div className="actions">
              {img && <>
                <button className="btn" onClick={() => onEdit(img.id)}><Wand2 size={15} /> Edit</button>
                <button className="btn primary" onClick={() => onToVideo(img.id)}><Film size={15} /> Jadikan video</button>
                <button className="btn" onClick={() => askCopy([img.id], [])}><Copy size={15} /> Salin ke workspace…</button>
                <a className="btn" href={api.imageUrl(img.id)} download={`gambar-${img.id.slice(0, 8)}.png`}><Download size={15} /> Unduh</a>
              </>}
              {clip?.status === "failed_download" &&
                <button className="btn" disabled={busy} onClick={() => run(() => api.retryDownload(clip.id))}>Coba unduh lagi (tanpa biaya baru)</button>}
              {clip?.status === "completed" && <>
                <button className="btn" onClick={() => setExtendOpen(!extendOpen)}><Layers size={15} /> Extend</button>
                {(clip.chain_depth > 0 || clip.has_merged) &&
                  <button className="btn" disabled={busy} onClick={() => run(async () => { await api.merge(clip.id); setMergedKey((k) => k + 1); })}>
                    {busy ? <Loader2 size={15} className="spin" /> : <ImageIcon size={15} />} Gabung rantai</button>}
                {clip.has_file && <button className="btn" onClick={() => onAddToFilm(clip.id)}><Clapperboard size={15} /> Ke storyboard</button>}
                {clip.has_file && <a className="btn" href={api.clipUrl(clip.id)} download={`klip-${clip.id.slice(0, 8)}.mp4`}><Download size={15} /> Unduh</a>}
              </>}
            </div>
            <div className="actions del">
              {confirmDel ? (<>
                <span className="muted">{clip ? "Video dan file-nya dihapus." : "Gambar dan file-nya dihapus."} Biaya tetap tercatat.</span>
                <button className="btn danger" disabled={busy} onClick={() => run(async () => {
                  if (img) await api.deleteImage(img.id); else await api.deleteClip(clip!.id);
                  onClose();
                })}>{busy ? <Loader2 size={15} className="spin" /> : <Trash2 size={15} />} Ya, hapus</button>
                <button className="btn ghost" onClick={() => setConfirmDel(false)}>Batal</button>
              </>) : (
                <button className="btn ghost danger" disabled={running} title={running ? "Tunggu job selesai" : undefined}
                  onClick={() => setConfirmDel(true)}><Trash2 size={15} /> Hapus</button>
              )}
            </div>
            {clip && mergedKey > 0 && (
              <div className="section"><h3>Hasil gabungan rantai</h3>
                <video key={mergedKey} src={`${api.mergedUrl(clip.id)}?v=${mergedKey}`} controls preload="metadata" /></div>
            )}
            {clip && extendOpen && <ExtendForm clip={clip} onDone={() => { setExtendOpen(false); reload(); }} />}
          </aside>
        </div>
      </div>
    </Portal>
  );
}
