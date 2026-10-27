// Halaman Komik (plan 21): satu panel = gambar AI (latar + karakter proyek sebagai referensi) + balon teks yang diedit di sini.
// Balon tidak pernah dikirim ke AI; digambar di <canvas> yang sama untuk tampilan dan unduh PNG.
import { PointerEvent as RPointerEvent, useEffect, useRef, useState } from "react";
import { BookOpen, Download, ImageIcon, Plus, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, Bubble, BubbleKind, Character, ComicPanel, ComicPanelPatch, EstimateRequest, workspace } from "../api";
import { useAsync } from "../components";
import { ModelPicker } from "../catalog";
import { EstimateLine, useConfirmedRun, useEstimate } from "../estimate";
import { useTrack } from "../queue";
import { SaveText } from "../storyboard/fields";
import { DEFAULT_IMAGE_MODEL } from "../storyboard/Generate";
import { EmptyState, Stage } from "../ui";
import { drawPanel } from "../comic/draw";

const SHOTS: [string, string][] = [["WS", "Lebar (WS)"], ["MS", "Sedang (MS)"], ["MCU", "Dada ke atas (MCU)"], ["CU", "Wajah (CU)"], ["ECU", "Sangat dekat (ECU)"]];
const ANGLES: [string, string][] = [["eye", "Sejajar mata"], ["low", "Dari bawah"], ["high", "Dari atas"], ["overhead", "Tegak dari atas"], ["dutch", "Miring (dutch)"]];
const STYLES: [string, string][] = [["project", "Ikut gaya proyek"], ["manga", "Manga hitam-putih"], ["western", "Komik Barat berwarna"], ["webtoon", "Webtoon"]];
const RATIOS = ["4:3", "3:4", "1:1", "16:9", "9:16", "3:2", "2:3"];
const KIND_LABEL: Record<BubbleKind, string> = { speech: "Bicara", thought: "Pikiran", caption: "Narasi", sfx: "Efek suara" };
const MAX_CAST = 4;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
/** Ukuran kanvas sebelum ada gambar: sisi panjang 1200 px mengikuti rasio panel. */
function ratioSize(r: string): [number, number] {
  const [a, b] = r.split(":").map(Number);
  return a >= b ? [1200, Math.round((1200 * b) / a)] : [Math.round((1200 * a) / b), 1200];
}
function newBubble(kind: BubbleKind, n: number): Bubble {
  const off = (n % 4) * 0.06;
  const base = { id: crypto.randomUUID().slice(0, 12), kind, character_id: null, x: 0.06 + off, y: 0.05 + off, tail_x: null, tail_y: null };
  if (kind === "caption") return { ...base, text: "Sementara itu…", w: 0.42, h: 0.12 };
  if (kind === "sfx") return { ...base, text: "BRAK!", w: 0.3, h: 0.16 };
  return { ...base, text: kind === "thought" ? "Hmm…" : "Halo!", w: 0.34, h: 0.18, tail_x: 0.06 + off + 0.2, tail_y: 0.05 + off + 0.3 };
}

export default function Comic({ characters, onGenerated }: { characters: Character[]; onGenerated: () => void }) {
  const panels = useAsync(api.comicPanels, []);
  const list = panels.data ?? [];
  const [sel, setSel] = useState<string | null>(null);
  const current = list.find((p) => p.id === sel) ?? list[0] ?? null;
  const replace = (p: ComicPanel) => panels.setData((xs) => (xs ?? []).map((x) => (x.id === p.id ? p : x)));

  async function add() {
    try {
      const p = await api.createComicPanel();
      panels.setData((xs) => [...(xs ?? []), p]);
      setSel(p.id);
    } catch (e) { toast.error((e as Error).message); }
  }
  async function remove(p: ComicPanel) {
    if (!window.confirm(`Hapus ${p.title}? Gambar take tetap ada di Library.`)) return;
    try {
      await api.deleteComicPanel(p.id);
      panels.setData((xs) => (xs ?? []).filter((x) => x.id !== p.id));
      setSel(null);
    } catch (e) { toast.error((e as Error).message); }
  }

  return (
    <Stage
      canvas={<>
        <div className="comic-tabs" role="tablist" aria-label="Panel komik">
          {list.map((p) => (
            <button key={p.id} role="tab" aria-selected={p.id === current?.id} className={`comic-tab ${p.id === current?.id ? "on" : ""}`} onClick={() => setSel(p.id)}>
              {p.image_id ? <img src={api.imageUrl(p.image_id)} alt="" /> : <span className="comic-tab-empty"><ImageIcon size={14} /></span>}
              <span>{p.title}</span>
            </button>
          ))}
          <button className="btn ghost sm" onClick={() => void add()}><Plus size={14} /> Panel baru</button>
        </div>
        {panels.error && <p className="error">{panels.error}</p>}
        {current
          ? <PanelEditor key={current.id} panel={current} replace={replace} />
          : panels.data && <EmptyState icon={<BookOpen size={36} />} title="Belum ada panel komik"
              hint="Satu panel = satu gambar dengan karakter dan latar proyek ini, lalu balon dialog yang bisa Anda geser.">
              <button className="btn primary" onClick={() => void add()}><Plus size={14} /> Buat panel pertama</button>
            </EmptyState>}
      </>}
      inspector={current
        ? <PanelInspector key={current.id} panel={current} characters={characters} replace={replace} onRemove={() => void remove(current)} onGenerated={onGenerated} />
        : <p className="muted">Buat panel untuk mulai.</p>}
    />
  );
}

/** Kanvas + balon yang bisa digeser, diubah ukuran, dan diarahkan ekornya. Simpan otomatis setelah berhenti mengubah. */
function PanelEditor({ panel, replace }: { panel: ComicPanel; replace: (p: ComicPanel) => void }) {
  const [bubbles, setBubbles] = useState<Bubble[]>(panel.bubbles);
  const [picked, setPicked] = useState<string | null>(null);
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const drag = useRef<{ id: string; mode: "move" | "resize" | "tail"; sx: number; sy: number; orig: Bubble } | null>(null);
  const dirty = useRef(false);
  const fallback = ratioSize(panel.aspect_ratio);
  const [W, H] = img ? [img.naturalWidth, img.naturalHeight] : fallback;   // lebar dibatasi tinggi layar tanpa merusak rasio

  // balon dari inspector (tambah, ubah teks, hapus) datang lewat panel.bubbles
  useEffect(() => { if (!dirty.current) setBubbles(panel.bubbles); }, [panel.bubbles]);
  useEffect(() => {
    if (!panel.image_id) { setImg(null); return; }
    const i = new Image();
    i.onload = () => setImg(i);
    i.src = api.imageUrl(panel.image_id);
  }, [panel.image_id]);
  useEffect(() => { if (canvas.current) drawPanel(canvas.current, img, bubbles, fallback); }, [img, bubbles, fallback[0], fallback[1]]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {   // simpan setelah 600 ms tanpa perubahan
    if (!dirty.current) return;
    const t = setTimeout(() => {
      api.updateComicPanel(panel.id, { bubbles })
        .then((p) => { dirty.current = false; replace(p); })
        .catch((e: Error) => toast.error(`Balon gagal disimpan: ${e.message}`));
    }, 600);
    return () => clearTimeout(t);
  }, [bubbles]);   // eslint-disable-line react-hooks/exhaustive-deps

  function down(e: RPointerEvent, id: string, mode: "move" | "resize" | "tail") {
    e.stopPropagation();
    e.preventDefault();
    setPicked(id);
    drag.current = { id, mode, sx: e.clientX, sy: e.clientY, orig: bubbles.find((b) => b.id === id)! };
    box.current?.setPointerCapture(e.pointerId);
  }
  function move(e: RPointerEvent) {
    const d = drag.current;
    if (!d || !box.current) return;
    const r = box.current.getBoundingClientRect();
    const dx = (e.clientX - d.sx) / r.width, dy = (e.clientY - d.sy) / r.height, o = d.orig;
    let n: Bubble;
    if (d.mode === "move") {
      const x = clamp(o.x + dx, 0, 1 - o.w), y = clamp(o.y + dy, 0, 1 - o.h);
      n = { ...o, x, y, tail_x: o.tail_x == null ? null : clamp(o.tail_x + x - o.x, 0, 1), tail_y: o.tail_y == null ? null : clamp(o.tail_y + y - o.y, 0, 1) };
    } else if (d.mode === "resize") n = { ...o, w: clamp(o.w + dx, 0.05, 1 - o.x), h: clamp(o.h + dy, 0.04, 1 - o.y) };
    else n = { ...o, tail_x: clamp((o.tail_x ?? 0) + dx, 0, 1), tail_y: clamp((o.tail_y ?? 0) + dy, 0, 1) };
    dirty.current = true;
    setBubbles((bs) => bs.map((b) => (b.id === d.id ? n : b)));
  }

  return (
    <div className="comic-wrap">
      <div ref={box} className="comic-box" onPointerMove={move} onPointerUp={() => { drag.current = null; }} onPointerDown={() => setPicked(null)}
        style={{ aspectRatio: `${W} / ${H}`, width: `min(100%, calc(72vh * ${W / H}))` }}>
        <canvas ref={canvas} aria-label={`Panel ${panel.title}`} />
        {bubbles.map((b) => (
          <div key={b.id} className={`cb-box ${picked === b.id ? "sel" : ""}`} title={`${KIND_LABEL[b.kind]}: ${b.text}`}
            style={{ left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.w * 100}%`, height: `${b.h * 100}%` }}
            onPointerDown={(e) => down(e, b.id, "move")}>
            {picked === b.id && <span className="cb-resize" onPointerDown={(e) => down(e, b.id, "resize")} aria-label="Ubah ukuran" />}
          </div>
        ))}
        {bubbles.filter((b) => picked === b.id && b.tail_x != null && b.tail_y != null).map((b) => (
          <span key={`t${b.id}`} className="cb-tail" style={{ left: `${b.tail_x! * 100}%`, top: `${b.tail_y! * 100}%` }}
            onPointerDown={(e) => down(e, b.id, "tail")} aria-label="Geser ekor balon" />
        ))}
      </div>
      <p className="muted">Geser balon untuk memindahkan, sudut kanan bawah untuk mengubah ukuran, titik kuning untuk mengarahkan ekor ke pembicara. Teks diedit di panel kanan.</p>
    </div>
  );
}

function PanelInspector({ panel, characters, replace, onRemove, onGenerated }: {
  panel: ComicPanel; characters: Character[]; replace: (p: ComicPanel) => void; onRemove: () => void; onGenerated: () => void;
}) {
  const locations = useAsync(api.locations, []);
  const [model, setModel] = useState("");
  const [picked, setPicked] = useState<string | null>(panel.bubbles[0]?.id ?? null);
  const [preview, setPreview] = useState<{ prompt: string; warnings: string[] } | null>(null);
  const track = useTrack();

  useEffect(() => {   // model bawaan = model gambar proyek
    void api.projectSettings(workspace.id).then((s) => setModel((m) => m || s.image_model || DEFAULT_IMAGE_MODEL)).catch(() => setModel((m) => m || DEFAULT_IMAGE_MODEL));
  }, []);
  useEffect(() => {
    if (!model) return;
    let alive = true;
    api.comicPreview(panel.id, model).then((p) => alive && setPreview(p)).catch(() => alive && setPreview(null));
    return () => { alive = false; };
  }, [panel.id, panel.updated_at, model]);

  async function patch(p: ComicPanelPatch) {
    try { replace(await api.updateComicPanel(panel.id, p)); }
    catch (e) { toast.error((e as Error).message); throw e; }
  }
  const quiet = (p: ComicPanelPatch) => { void patch(p).catch(() => {}); };

  const body: (EstimateRequest & { v?: string }) | null = model ? { kind: "comic_panel", model, panel_id: panel.id, v: panel.updated_at } : null;
  const live = useEstimate(body);
  const runner = useConfirmedRun(() => body, async (c) => {
    replace(await track(`Panel komik: ${panel.title}`, () => api.generateComicPanel(panel.id, { model, ...c })));
    onGenerated();
  });

  const bubble = panel.bubbles.find((b) => b.id === picked) ?? null;
  const setBubble = (b: Bubble) => quiet({ bubbles: panel.bubbles.map((x) => (x.id === b.id ? b : x)) });
  function addBubble(kind: BubbleKind) {
    const b = newBubble(kind, panel.bubbles.length);
    setPicked(b.id);
    quiet({ bubbles: [...panel.bubbles, b] });
  }
  function toggleChar(id: string) {
    const has = panel.character_ids.includes(id);
    if (!has && panel.character_ids.length >= MAX_CAST) { toast(`Maksimal ${MAX_CAST} karakter per panel`); return; }
    quiet({ character_ids: has ? panel.character_ids.filter((c) => c !== id) : [...panel.character_ids, id] });
  }
  async function download() {
    if (!panel.image_id) return;
    const img = new Image();
    img.src = api.imageUrl(panel.image_id);
    await img.decode();
    const c = document.createElement("canvas");
    drawPanel(c, img, panel.bubbles, ratioSize(panel.aspect_ratio));
    c.toBlob((blob) => {
      if (!blob) { toast.error("Gagal membuat PNG"); return; }
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${panel.title.replace(/[^\w\- ]+/g, "").trim() || "panel"}.png`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    }, "image/png");
  }

  return (
    <div className="comic-inspector">
      <label className="field">Judul
        <SaveText label="Judul panel" maxLength={120} value={panel.title} onSave={(v) => patch({ title: v })} />
      </label>
      <label className="field">Apa yang terjadi di panel ini
        <SaveText label="Deskripsi panel" multiline rows={3} maxLength={2000} value={panel.description}
          placeholder="Contoh: Momon mengintip dari balik pintu dapur, matanya terbelalak melihat kue di meja"
          onSave={(v) => patch({ description: v })} />
        <span className="muted">Dialog jangan ditulis di sini; tulis di balon supaya AI tidak menggambar teks.</span>
      </label>

      <div className="field" role="group" aria-label="Karakter di panel">Karakter ({panel.character_ids.length}/{MAX_CAST})
        <div className="chips">
          {characters.map((c) => (
            <button key={c.id} type="button" className={`chip ${panel.character_ids.includes(c.id) ? "on" : ""}`} aria-pressed={panel.character_ids.includes(c.id)}
              onClick={() => toggleChar(c.id)}>{c.name}</button>
          ))}
          {characters.length === 0 && <span className="muted">Belum ada karakter di proyek ini.</span>}
        </div>
      </div>
      <label className="field">Latar
        <select value={panel.location_id ?? ""} onChange={(e) => quiet({ location_id: e.target.value || null })}>
          <option value="">Tanpa latar</option>
          {(locations.data ?? []).map((l) => <option key={l.id} value={l.id}>{l.name}{l.image_id ? "" : " (tanpa gambar)"}</option>)}
        </select>
      </label>
      <div className="comic-grid2">
        <label className="field">Shot
          <select value={panel.shot} onChange={(e) => quiet({ shot: e.target.value })}>{SHOTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        </label>
        <label className="field">Sudut kamera
          <select value={panel.angle} onChange={(e) => quiet({ angle: e.target.value })}>{ANGLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        </label>
        <label className="field">Rasio
          <select value={panel.aspect_ratio} onChange={(e) => quiet({ aspect_ratio: e.target.value })}>{RATIOS.map((r) => <option key={r}>{r}</option>)}</select>
        </label>
        <label className="field">Gaya
          <select value={panel.comic_style} onChange={(e) => quiet({ comic_style: e.target.value })}>{STYLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        </label>
      </div>

      <ModelPicker kind="image" label="Model gambar" value={model} onChange={setModel} />
      {preview?.warnings.map((w) => <p key={w} className="muted warn">{w}</p>)}
      <EstimateLine est={live.est} error={live.error} />
      {runner.error && <p className="error">{runner.error}</p>}
      <button className="btn primary block" disabled={!model || !!live.error || !live.est || !!live.est.blocked} onClick={() => void runner.start()}>
        <Sparkles size={14} /> {panel.image_id ? "Buat take baru" : "Buat gambar panel"}
      </button>
      {runner.dialog}
      {panel.takes.length > 1 && <>
        <span className="muted">Take (yang terbaru otomatis dipakai; klik untuk kembali ke take lain)</span>
        <div className="pick-grid">{panel.takes.map((id) => (
          <button key={id} className={`thumb ${id === panel.image_id ? "sel" : ""}`} aria-label="Pakai take ini" onClick={() => quiet({ image_id: id })}>
            <img src={api.imageUrl(id)} alt="" loading="lazy" />
          </button>
        ))}</div>
      </>}
      {preview && <details><summary>Prompt yang dikirim ke model gambar</summary><pre className="prompt-pre">{preview.prompt}</pre></details>}

      <h4>Balon</h4>
      <div className="chips">
        {(Object.keys(KIND_LABEL) as BubbleKind[]).map((k) => (
          <button key={k} type="button" className="btn ghost sm" disabled={panel.bubbles.length >= 20} onClick={() => addBubble(k)}><Plus size={12} /> {KIND_LABEL[k]}</button>
        ))}
      </div>
      {panel.bubbles.length > 0 && (
        <div className="chips" role="listbox" aria-label="Pilih balon">
          {panel.bubbles.map((b, i) => (
            <button key={b.id} type="button" className={`chip ${b.id === picked ? "on" : ""}`} onClick={() => setPicked(b.id)}>{i + 1}. {KIND_LABEL[b.kind]}</button>
          ))}
        </div>
      )}
      {bubble && <BubbleFields key={bubble.id} bubble={bubble} characters={characters.filter((c) => panel.character_ids.includes(c.id))} onChange={setBubble}
        onDelete={() => { setPicked(null); quiet({ bubbles: panel.bubbles.filter((b) => b.id !== bubble.id) }); }} />}

      <div className="actions">
        <button className="btn" disabled={!panel.image_id} onClick={() => void download()} title={panel.image_id ? "" : "Buat gambar panel dulu"}><Download size={14} /> Unduh PNG</button>
        <button className="btn ghost danger" onClick={onRemove}><Trash2 size={14} /> Hapus panel</button>
      </div>
    </div>
  );
}

function BubbleFields({ bubble, characters, onChange, onDelete }: { bubble: Bubble; characters: Character[]; onChange: (b: Bubble) => void; onDelete: () => void }) {
  const [text, setText] = useState(bubble.text);
  useEffect(() => {   // simpan teks setelah berhenti mengetik; teks kosong tidak dikirim (server menolaknya)
    if (text === bubble.text || !text.trim()) return;
    const t = setTimeout(() => onChange({ ...bubble, text }), 500);
    return () => clearTimeout(t);
  }, [text]);   // eslint-disable-line react-hooks/exhaustive-deps
  const tail = bubble.kind === "speech" || bubble.kind === "thought";
  return (
    <div className="comic-bubble-fields">
      <label className="field">Teks {KIND_LABEL[bubble.kind].toLowerCase()}
        <textarea rows={2} maxLength={300} value={text} onChange={(e) => setText(e.target.value)} />
        {!text.trim() && <span className="muted warn">Teks kosong tidak disimpan.</span>}
      </label>
      {tail && <>
        <label className="field">Pembicara
          <select value={bubble.character_id ?? ""} onChange={(e) => onChange({ ...bubble, character_id: e.target.value || null })}>
            <option value="">Tidak ditentukan</option>
            {characters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={bubble.tail_x != null}
            onChange={(e) => onChange(e.target.checked
              ? { ...bubble, tail_x: clamp(bubble.x + bubble.w / 2, 0, 1), tail_y: clamp(bubble.y + bubble.h + 0.12, 0, 1) }
              : { ...bubble, tail_x: null, tail_y: null })} />
          Ekor balon
        </label>
      </>}
      <button className="btn ghost sm danger" onClick={onDelete}><Trash2 size={12} /> Hapus balon</button>
    </div>
  );
}
