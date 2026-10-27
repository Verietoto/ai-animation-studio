import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Check, Copy, Film, ImageIcon, Loader2, Search, Trash2, UserRound } from "lucide-react";
import { toast } from "sonner";
import { useWorkspaces } from "../workspaces";
import { api, Character, Clip, Img } from "../api";
import { ItemRef } from "../lightbox";
import { ACTIVE } from "../queue";
import { EmptyState, Portal } from "../ui";

type Filter = "all" | "image" | "video" | "character";
const FILTERS: [Filter, string][] = [["all", "Semua"], ["image", "Gambar"], ["video", "Video"], ["character", "Karakter"]];
const SERVER_LIMIT = 200;   // LIMIT di GET /api/images dan /api/clips

type Entry =
  | { type: "image"; id: string; at: string; text: string; img: Img }
  | { type: "clip"; id: string; at: string; text: string; clip: Clip }
  | { type: "character"; id: string; at: string; text: string; ch: Character };

/** Video hanya dipasang saat kartu terlihat; diputar saat hover (perangkat dengan hover, tanpa reduced motion). */
function ClipThumb({ clip }: { clip: Clip }) {
  const box = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = box.current; if (!el) return;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setSeen(true); io.disconnect(); } }, { rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  const canHover = () => matchMedia("(hover: hover)").matches && !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const running = ACTIVE.includes(clip.status);
  return (
    <div ref={box} className="tile-media"
      onMouseEnter={() => { if (canHover()) void video.current?.play().catch(() => {}); }}
      onMouseLeave={() => { const v = video.current; if (v) { v.pause(); v.currentTime = 0; } }}>
      {clip.has_file && seen
        ? <video ref={video} src={`${api.clipUrl(clip.id)}#t=0.1`} muted loop playsInline preload="metadata" />
        : <div className="placeholder" style={{ height: "100%", margin: 0 }}>
            {running ? <Loader2 className="spin" /> : clip.status === "failed" || clip.status === "failed_download" ? <AlertTriangle /> : <Film />}
          </div>}
      {clip.status !== "completed" && <span className={`pill ${clip.status} tile-badge`}>{clip.status}</span>}
    </div>
  );
}

/** Dialog konfirmasi hapus-banyak: rincian per jenis, yang tersembunyi filter, dan akibatnya. */
function BulkDeleteDialog({ picked, hidden, onClose, onDone }: {
  picked: Set<string>; hidden: number; onClose: () => void; onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ids = (type: string) => [...picked].filter((k) => k.startsWith(`${type}:`)).map((k) => k.slice(type.length + 1));
  const [im, cl, ch] = [ids("image"), ids("clip"), ids("character")];
  async function confirm() {
    setBusy(true); setError(null);
    try {
      const r = await api.bulkDelete({ image_ids: im, clip_ids: cl, character_ids: ch });
      const n = r.deleted.images + r.deleted.clips + r.deleted.characters;
      if (r.failed.length === 0) toast.success(`${n} item dihapus`);
      else toast.warning(`${n} dihapus, ${r.failed.length} gagal`, { description: r.failed.slice(0, 5).map((f) => f.reason).join(" · "), duration: 15000 });
      onDone();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <Portal>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Hapus item terpilih"
        onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}
        onKeyDown={(e) => { if (e.key === "Escape" && !busy) onClose(); }}>
        <div className="modal-box">
          <h3>Hapus {picked.size} item?</h3>
          <p><strong>{im.length} gambar, {cl.length} video, {ch.length} karakter</strong></p>
          {hidden > 0 && <p className="error">{hidden} dari item ini sedang tersembunyi oleh filter atau pencarian.</p>}
          <ul className="muted">
            <li>Berkas dihapus dari disk dan tidak bisa dikembalikan. Biaya yang sudah keluar tetap terhitung di anggaran harian.</li>
            <li>Keyframe adegan Storyboard yang memakai gambar ini jadi kosong.</li>
            <li>Gambar karakter yang tidak ikut dipilih tetap ada. Item yang masih dipakai item lain dilewati dan dilaporkan.</li>
          </ul>
          {error && <p className="error">{error}</p>}
          <div className="actions">
            <button className="btn" onClick={onClose} disabled={busy}>Batal</button>
            <button className="btn danger-solid" onClick={confirm} disabled={busy}>
              {busy ? <><Loader2 size={15} className="spin" /> Menghapus…</> : `Hapus ${picked.size} permanen`}
            </button>
          </div>
        </div>
      </div>
    </Portal>
  );
}

export default function Library({ images, clips, characters, onOpen, onCharacters, reload }: {
  images: Img[]; clips: Clip[]; characters: Character[]; onOpen: (r: ItemRef) => void; onCharacters: () => void; reload: () => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const { askCopy } = useWorkspaces();
  const [selecting, setSelecting] = useState(false);   // mode pilih-banyak: salin ke workspace lain (gambar & karakter) atau hapus (semua)
  const [deleting, setDeleting] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const pick = (key: string) => setPicked((p) => { const n = new Set(p); if (n.has(key)) n.delete(key); else n.add(key); return n; });
  const stopSelecting = () => { setSelecting(false); setPicked(new Set()); };
  const copyPicked = () => {
    const ids = (type: string) => [...picked].filter((k) => k.startsWith(`${type}:`)).map((k) => k.slice(type.length + 1));
    askCopy(ids("image"), ids("character"));
    stopSelecting();
  };
  // pilihan dibersihkan dari item yang sudah tidak ada (terhapus / pindah workspace)
  useEffect(() => {
    const alive = new Set([...images.map((i) => `image:${i.id}`), ...clips.map((c) => `clip:${c.id}`), ...characters.map((c) => `character:${c.id}`)]);
    setPicked((p) => (p.size === 0 || [...p].every((k) => alive.has(k)) ? p : new Set([...p].filter((k) => alive.has(k)))));
  }, [images, clips, characters]);

  const entries = useMemo<Entry[]>(() => {
    const all: Entry[] = [
      ...images.map((img): Entry => ({ type: "image", id: img.id, at: img.created_at, text: `${img.prompt?.split("\n---\n")[0] ?? ""} ${img.model ?? ""} ${img.kind}`, img })),
      ...clips.map((clip): Entry => ({ type: "clip", id: clip.id, at: clip.created_at, text: `${clip.prompt} ${clip.model} ${clip.status}`, clip })),
      ...characters.map((ch): Entry => ({ type: "character", id: ch.id, at: ch.created_at ?? "", text: `${ch.name} ${ch.description}`, ch })),
    ];
    const needle = q.trim().toLowerCase();
    return all
      .filter((e) => (filter === "all" || (filter === "video" ? e.type === "clip" : e.type === filter)) && (!needle || e.text.toLowerCase().includes(needle)))
      .sort((a, b) => b.at.localeCompare(a.at));
  }, [images, clips, characters, filter, q]);

  const visible = new Set(entries.map((e) => `${e.type}:${e.id}`));
  const hidden = [...picked].filter((k) => !visible.has(k)).length;
  const copyable = [...picked].filter((k) => !k.startsWith("clip:")).length;
  const truncated = images.length >= SERVER_LIMIT || clips.length >= SERVER_LIMIT;
  return (
    <div className="full">
      <div className="toolbar">
        <div className="seg" role="tablist" aria-label="Filter jenis">
          {FILTERS.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={filter === id} className={filter === id ? "on" : ""} onClick={() => setFilter(id)}>{label}</button>
          ))}
        </div>
        <label className="search"><Search size={14} />
          <input placeholder="Cari prompt, model, nama…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Cari di library" /></label>
        <span className="muted">{entries.length} item</span>
        <button className={`btn sm ${selecting ? "primary" : ""}`} onClick={() => (selecting ? stopSelecting() : setSelecting(true))}
          title="Pilih beberapa item untuk disalin ke workspace lain atau dihapus">
          <Copy size={14} /> {selecting ? "Selesai memilih" : "Pilih banyak"}
        </button>
      </div>
      {truncated && <p className="muted">Menampilkan {SERVER_LIMIT} terbaru per jenis; yang lebih lama tidak dimuat.</p>}
      {entries.length === 0 && (
        <EmptyState icon={<ImageIcon size={36} />} title={q || filter !== "all" ? "Tidak ada yang cocok" : "Library masih kosong"}
          hint={q || filter !== "all" ? "Coba filter atau kata kunci lain." : "Unggah gambar atau buat video; semuanya muncul di sini."} />
      )}
      <div className="tiles">
        {entries.map((e) => (
          <button key={`${e.type}${e.id}`} className={`tile ${picked.has(`${e.type}:${e.id}`) ? "picked" : ""}`}
            aria-pressed={selecting ? picked.has(`${e.type}:${e.id}`) : undefined}
            onClick={() => (selecting ? pick(`${e.type}:${e.id}`) : e.type === "character" ? onCharacters() : onOpen({ type: e.type, id: e.id }))}
            aria-label={e.type === "character" ? `Karakter ${e.ch.name}` : `${e.type === "image" ? "Gambar" : "Video"}: ${e.text.slice(0, 60)}`}>
            {e.type === "image" && <div className="tile-media"><img src={api.imageUrl(e.id)} alt="" loading="lazy" /></div>}
            {e.type === "clip" && <ClipThumb clip={e.clip} />}
            {e.type === "character" && <div className="tile-media"><img src={api.imageUrl(e.ch.source_image_id)} alt="" loading="lazy" /></div>}
            {selecting && <span className="tile-check" aria-hidden>{picked.has(`${e.type}:${e.id}`) && <Check size={14} />}</span>}
            <span className="tile-cap">
              {e.type === "image" ? <ImageIcon size={12} /> : e.type === "clip" ? <Film size={12} /> : <UserRound size={12} />}
              <span className="clamp1">{e.type === "character" ? e.ch.name : e.type === "clip" ? e.clip.prompt : e.img.prompt?.split("\n---\n")[0] ?? e.img.kind}</span>
            </span>
          </button>
        ))}
      </div>
      {selecting && (
        <div className="pickbar" role="region" aria-label="Aksi salin">
          <span>{picked.size} dipilih{hidden > 0 && ` (${hidden} tersembunyi)`}</span>
          <button className="btn" disabled={entries.length === 0} onClick={() => setPicked((p) => new Set([...p, ...visible]))}>Pilih semua yang terlihat</button>
          <button className="btn" disabled={picked.size === 0} onClick={() => setPicked(new Set())}>Kosongkan</button>
          <button className="btn" disabled={copyable === 0} onClick={copyPicked} title="Video tidak ikut disalin"><Copy size={15} /> Salin ({copyable})…</button>
          <button className="btn danger-solid" disabled={picked.size === 0} onClick={() => setDeleting(true)}><Trash2 size={15} /> Hapus ({picked.size})</button>
          <button className="btn ghost" onClick={stopSelecting}>Batal</button>
        </div>
      )}
      {deleting && <BulkDeleteDialog picked={picked} hidden={hidden} onClose={() => setDeleting(false)}
        onDone={() => { setDeleting(false); stopSelecting(); reload(); }} />}
    </div>
  );
}
