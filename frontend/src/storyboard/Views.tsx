import { closestCenter, DndContext, DragEndEvent, KeyboardSensor, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { arrayMove, rectSortingStrategy, SortableContext, sortableKeyboardCoordinates, useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Clapperboard, Download, Film as FilmIcon, GripVertical, ListChecks, Loader2, Play, Plus, Trash2, X } from "lucide-react";
import { api, Character, FilmDetail, Location, Scene, SceneStatus, SceneUpdate } from "../api";
import { EmptyState } from "../ui";
import { CastEditor, SaveText } from "./fields";

export const STATUS_LABEL: Record<SceneStatus, string> = {
  naskah: "naskah", keyframe: "keyframe", video_diproses: "video diproses", siap: "siap", gagal: "video gagal",
};
const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

function SceneMedia({ scene }: { scene: Scene }) {
  if (scene.clip_id && scene.clip_status === "completed") return <video src={`${api.clipUrl(scene.clip_id)}#t=0.1`} muted preload="metadata" playsInline />;
  if (scene.keyframe_image_id) return <img src={api.imageUrl(scene.keyframe_image_id)} alt="" loading="lazy" />;
  if (scene.location?.image_id) return <img className="dim" src={api.imageUrl(scene.location.image_id)} alt="" loading="lazy" />;
  return <div className="placeholder" style={{ height: "100%", margin: 0 }}><Clapperboard size={20} /></div>;
}

const snippet = (s: Scene) => s.cast.find((c) => c.action)?.action ?? s.dialogue;

/** Hapus dua langkah: ikon sampah, lalu "Ya" / batal. */
function DeleteBtn({ number, disabled, onConfirm }: { number: number; disabled: boolean; onConfirm: () => void }) {
  const [ask, setAsk] = useState(false);
  if (!ask) return <button className="btn ghost sm" disabled={disabled} aria-label={`Hapus adegan ${number}`} title="Hapus adegan" onClick={(e) => { e.stopPropagation(); setAsk(true); }}><Trash2 size={14} /></button>;
  return (
    <span className="del-ask" onClick={(e) => e.stopPropagation()}>
      <button className="btn danger sm" onClick={onConfirm}>Hapus?</button>
      <button className="btn ghost sm" aria-label="Batal hapus" onClick={() => setAsk(false)}><X size={13} /></button>
    </span>
  );
}

function SceneCard({ scene, selected, locked, picking, picked, onSelect, onPick, onDelete }: {
  scene: Scene; selected: boolean; locked: boolean; picking: boolean; picked: boolean;
  onSelect: () => void; onPick: (range: boolean) => void; onDelete: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: scene.id, disabled: locked || picking });
  return (
    <li ref={setNodeRef} className={`scene-card ${selected && !picking ? "on" : ""} ${picked ? "picked" : ""} ${isDragging ? "drag" : ""}`}
      style={{ transform: CSS.Transform.toString(transform), transition }}>
      <div className="scene-card-main" role="button" tabIndex={0} aria-pressed={picking ? picked : selected} aria-label={picking ? `Pilih adegan ${scene.number}` : `Adegan ${scene.number}`}
        onClick={(e) => (picking ? onPick(e.shiftKey) : onSelect())}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (picking) onPick(e.shiftKey); else onSelect(); } }}>
        <div className="scene-media">
          <SceneMedia scene={scene} />
          {picking && <span className={`scene-check ${picked ? "on" : ""}`} aria-hidden>{picked && <Check size={14} />}</span>}
          <span className="scene-n">{scene.number}</span>
          <span className={`pill st-${scene.status}`}>{STATUS_LABEL[scene.status]}</span>
        </div>
        <strong className="clamp1">{scene.location?.name ?? "Tanpa latar"}{scene.time_of_day ? ` · ${scene.time_of_day}` : ""}</strong>
        <span className="muted clamp1">{scene.cast.length ? scene.cast.map((c) => c.character_name).join(", ") : "Tanpa pemeran"}</span>
        <span className="muted clamp2">{snippet(scene) || "Belum ada aksi"}</span>
        {scene.planned_seconds ? <span className="mono muted">rencana {scene.planned_seconds}d</span> : null}
      </div>
      {!picking && <div className="card-tools">
        <DeleteBtn number={scene.number} disabled={locked} onConfirm={onDelete} />
        <button className="btn ghost sm grip" disabled={locked} {...attributes} {...listeners} aria-label={`Geser adegan ${scene.number}`}><GripVertical size={14} /></button>
      </div>}
    </li>
  );
}

/** Papan: kartu adegan berurutan, geser untuk mengurutkan. */
export function Board({ scenes, selectedId, locked, onSelect, onReorder, onAdd, onDelete, onBulkDelete }: {
  scenes: Scene[]; selectedId: string | null; locked: boolean;
  onSelect: (id: string) => void; onReorder: (ids: string[]) => void; onAdd: () => void; onDelete: (id: string) => void;
  /** Bila ada, papan punya mode "Pilih beberapa" (klik memilih, Shift+klik memilih rentang) dan menghapus semuanya sekaligus. */
  onBulkDelete?: (ids: string[]) => Promise<unknown>;
}) {
  const [picking, setPicking] = useState(false);
  const [pickedRaw, setPicked] = useState<string[]>([]);
  const [deleting, setDeleting] = useState(false);
  const anchor = useRef<number | null>(null);
  const picked = pickedRaw.filter((id) => scenes.some((s) => s.id === id));   // adegan yang sudah hilang dari daftar tidak ikut terhitung
  const stopPicking = () => { setPicking(false); setPicked([]); anchor.current = null; };
  useEffect(() => {
    if (!picking) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") stopPicking(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [picking]);
  const pick = (i: number, range: boolean) => {
    const id = scenes[i].id;
    setPicked((cur) => {
      if (range && anchor.current != null) {
        const [a, b] = [Math.min(anchor.current, i), Math.max(anchor.current, i)];
        return [...new Set([...cur, ...scenes.slice(a, b + 1).map((s) => s.id)])];
      }
      return cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
    });
    anchor.current = i;
  };
  async function deletePicked() {
    if (!onBulkDelete || !picked.length) return;
    const nums = scenes.filter((s) => picked.includes(s.id)).map((s) => s.number).join(", ");
    if (!window.confirm(`Hapus ${picked.length} adegan (nomor ${nums})? Beat dan pemerannya ikut dihapus; keyframe dan video tetap ada di Library.`)) return;
    setDeleting(true);
    try { await onBulkDelete(picked); stopPicking(); } catch { /* galat sudah ditampilkan pemanggil; pilihan dipertahankan */ } finally { setDeleting(false); }
  }
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const onDragEnd = (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return;
    const from = scenes.findIndex((s) => s.id === e.active.id), to = scenes.findIndex((s) => s.id === e.over!.id);
    onReorder(arrayMove(scenes, from, to).map((s) => s.id));
  };
  return (
    <>
      {onBulkDelete && scenes.length > 1 && (picking
        ? <div className="board-tools picking" role="toolbar" aria-label="Pilih beberapa adegan">
            <strong aria-live="polite">{picked.length} dipilih</strong>
            <button className="btn sm" onClick={() => setPicked(scenes.map((s) => s.id))}>Pilih semua</button>
            <button className="btn sm" disabled={!picked.length} onClick={() => setPicked([])}>Kosongkan</button>
            <button className="btn danger sm" disabled={!picked.length || deleting || locked} onClick={() => void deletePicked()}>
              {deleting ? <Loader2 size={13} className="spin" /> : <Trash2 size={13} />} Hapus {picked.length || ""} adegan
            </button>
            <button className="btn ghost sm" onClick={stopPicking}>Selesai</button>
            <span className="muted">Shift+klik memilih rentang. Esc untuk keluar.</span>
          </div>
        : <div className="board-tools"><button className="btn ghost sm" disabled={locked} onClick={() => setPicking(true)}><ListChecks size={14} /> Pilih beberapa</button></div>)}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={scenes.map((s) => s.id)} strategy={rectSortingStrategy}>
          <ol className="board">
            {scenes.map((s, i) => <SceneCard key={s.id} scene={s} selected={s.id === selectedId} locked={locked} picking={picking} picked={picked.includes(s.id)}
              onSelect={() => onSelect(s.id)} onPick={(range) => pick(i, range)} onDelete={() => onDelete(s.id)} />)}
            {!picking && <li><button className="scene-add" disabled={locked} onClick={onAdd} aria-label="Tambah adegan"><Plus size={20} />{scenes.length ? "Adegan" : "Adegan pertama"}</button></li>}
          </ol>
        </SortableContext>
      </DndContext>
    </>
  );
}

/** Naskah: satu baris per adegan, semua kolom teks bisa diketik langsung. */
export function ScriptView({ scenes, selectedId, focusId, locked, locations, characters, onSelect, onPatch, onAdd, onDelete }: {
  scenes: Scene[]; selectedId: string | null; focusId: string | null; locked: boolean; locations: Location[]; characters: Character[];
  onSelect: (id: string) => void; onPatch: (id: string, body: SceneUpdate) => Promise<unknown>; onAdd: (after?: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="script" role="table" aria-label="Naskah episode">
      <div className="script-row script-head" role="row">
        <span>#</span><span>Latar & waktu</span><span>Pemeran & aksi</span><span>Dialog / catatan</span>
      </div>
      {scenes.map((s, i) => (
        <div key={s.id} role="row" className={`script-row ${s.id === selectedId ? "on" : ""}`} onFocus={() => onSelect(s.id)} onClick={() => onSelect(s.id)}>
          <div className="script-num"><span className="scene-n static">{s.number}</span><DeleteBtn number={s.number} disabled={locked} onConfirm={() => onDelete(s.id)} /></div>
          <div className="script-col">
            <select aria-label={`Latar adegan ${s.number}`} value={s.location?.id ?? ""} disabled={locked}
              onChange={(e) => void onPatch(s.id, { location_id: e.target.value || null }).catch(() => {})}>
              <option value="">(tanpa latar)</option>
              {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
            <SaveText label={`Waktu adegan ${s.number}`} value={s.time_of_day} maxLength={60} placeholder="waktu, mis. senja"
              autoFocus={s.id === focusId} onSave={(v) => onPatch(s.id, { time_of_day: v })} />
          </div>
          <CastEditor key={s.id} scene={s} characters={characters} locked={locked} onSave={(cast) => onPatch(s.id, { cast })} />
          <SaveText label={`Dialog adegan ${s.number}`} value={s.dialogue} maxLength={1000}
            placeholder="dialog atau catatan (tidak dikirim ke AI)" onSave={(v) => onPatch(s.id, { dialogue: v })}
            onEnter={i === scenes.length - 1 ? () => onAdd(s.id) : undefined} />
        </div>
      ))}
      <button className="btn block" disabled={locked} onClick={() => onAdd(scenes[scenes.length - 1]?.id)}><Plus size={14} /> Adegan baru</button>
    </div>
  );
}

/** Timeline: hasil render episode + urutan video per adegan. */
export function TimelineView({ detail, rendering, onRender }: { detail: FilmDetail; rendering: boolean; onRender: () => void }) {
  const total = detail.scenes.reduce((sum, s) => sum + (s.clip_id ? detail.durations[s.clip_id] ?? 0 : 0), 0);
  const blocked = detail.warnings.some((w) => w.kind === "unplayable");
  return (
    <>
      <div className="preview sb-player">
        {detail.has_file
          ? <video key={detail.updated_at} src={api.filmUrl(detail.id, detail.updated_at)} controls playsInline />
          : <EmptyState icon={rendering ? <Loader2 size={36} className="spin" /> : <Play size={36} />}
              title={rendering ? "Merender episode…" : "Belum dirender"} hint={rendering ? "Boleh pindah halaman; render tetap berjalan." : "Setiap adegan butuh video, lalu klik Render episode."} />}
        {detail.has_file && rendering && <span className="chip meta"><Loader2 size={12} className="spin" /> merender ulang…</span>}
      </div>
      {detail.stale && !rendering && <p className="muted"><AlertTriangle size={13} /> Adegan berubah sejak render terakhir; video di atas belum mencerminkannya.</p>}
      {detail.render_status === "failed" && <p className="error">{detail.render_error}</p>}
      {detail.warnings.map((w) => <p key={`${w.kind}${w.scene}`} className="warn"><AlertTriangle size={13} /> {w.message}</p>)}
      <div className="actions">
        <button className="btn primary" disabled={rendering || detail.scenes.length === 0 || blocked} onClick={onRender}>
          {rendering ? <Loader2 size={15} className="spin" /> : <FilmIcon size={15} />} Render episode
        </button>
        {detail.has_file && <a className="btn" href={api.filmUrl(detail.id, detail.updated_at)} download={`${detail.title}.mp4`}><Download size={15} /> Unduh</a>}
        <span className="muted">Render tidak memakai AI, jadi gratis. Total jadi {fmt(total)}{detail.planned_seconds ? `, rencana ${fmt(detail.planned_seconds)}` : ""}.</span>
      </div>
      <ol className="order-list">
        {detail.scenes.map((s) => (
          <li key={s.id}>
            <span className="scene-n static">{s.number}</span>
            <span className="clamp1">{s.location?.name ?? "Tanpa latar"}{s.time_of_day ? ` · ${s.time_of_day}` : ""}</span>
            <span className={`pill st-${s.status}`}>{STATUS_LABEL[s.status]}</span>
            <span className="mono muted" title="jadi / rencana">{s.clip_id && detail.durations[s.clip_id] != null ? `${detail.durations[s.clip_id].toFixed(1)}d` : "—"}{s.planned_seconds ? ` / ${s.planned_seconds}d` : ""}</span>
          </li>
        ))}
      </ol>
    </>
  );
}
