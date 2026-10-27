import { lazy, ReactNode, Suspense, useState } from "react";
import { Box, Copy, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { api, Character, Clip, Img, Location, Scene, SceneUpdate } from "../api";
import { Section } from "../ui";
import { CastEditor, SaveText } from "./fields";
import { KeyframePanel, PrevisVideoPanel, Takes, VideoPanel } from "./Generate";
import { STATUS_LABEL } from "./Views";
import { ScenePromptEditor } from "./v2/ScenePrompt";

const Blockout = lazy(() => import("./Blockout"));   // three.js hanya dimuat saat editor 3D dibuka (plan 14)

const CAMERA_HINTS = ["dolly in", "dolly out", "pan kiri", "pan kanan", "orbit", "crane naik", "handheld", "close-up", "wide shot"];
const TIME_HINTS = ["pagi", "siang", "senja", "malam", "fajar"];

/** Pilih satu gambar/klip dari library (dilipat supaya inspector tetap ringkas). */
function PickGrid({ title, children, empty }: { title: string; children: ReactNode; empty?: string }) {
  return (
    <details className="pick">
      <summary>{title}</summary>
      <div className="pick-grid">{children}</div>
      {empty && <p className="muted">{empty}</p>}
    </details>
  );
}

export function SceneInspector({ scene, aspect, locked, locations, characters, images, clips, onPatch, onDelete, onDuplicate, onNewLocation, onManageLocations, onGenerated, promptMode }: {
  scene: Scene; aspect: string; locked: boolean; locations: Location[]; characters: Character[]; images: Img[]; clips: Clip[];
  onPatch: (body: SceneUpdate) => Promise<unknown>; onDelete: () => void; onDuplicate: () => void;
  onNewLocation: (name: string) => Promise<Location>; onManageLocations: () => void; onGenerated: () => void;
  promptMode?: boolean;   // Storyboard v2: prompt adegan jadi satu-satunya sumber latar/pemeran/beat/mood/durasi (plan 18 Revisi 8)
}) {
  const [confirmDel, setConfirmDel] = useState(false);
  const [newLoc, setNewLoc] = useState<string | null>(null);
  const [blockoutOpen, setBlockoutOpen] = useState(false);
  const ready = clips.filter((c) => c.status === "completed" && c.has_file).slice(0, 60);
  const guard = (fn: () => Promise<unknown>) => void fn().catch(() => {});   // pesan galat sudah ditampilkan oleh onPatch

  async function createLocation() {
    const name = (newLoc ?? "").trim();
    if (!name) return;
    try {
      const loc = await onNewLocation(name);
      await onPatch({ location_id: loc.id });
      setNewLoc(null);
    } catch (e) { toast.error((e as Error).message); }
  }

  return (
    <>
      <div className="insp-head">
        <h3>Adegan {scene.number}</h3>
        <span className={`pill st-${scene.status}`}>{STATUS_LABEL[scene.status]}</span>
        <button className="btn ghost sm" onClick={onDuplicate} disabled={locked} title="Duplikat naskah adegan" aria-label="Duplikat adegan"><Copy size={14} /></button>
      </div>
      {locked && <p className="warn">Episode sedang dirender; struktur dikunci, teks tetap bisa diubah.</p>}

      {promptMode && <Section title="Prompt adegan"><ScenePromptEditor scene={scene} characters={characters} locations={locations} locked={locked} rows={14} onSaved={onGenerated} /></Section>}

      {!promptMode && scene.script_excerpt && <p className="muted jr-excerpt" title="Potongan naskah asal adegan ini">Dari naskah: {scene.script_excerpt}</p>}

      {!promptMode && <Section title="Latar">
        <select aria-label="Latar" value={scene.location?.id ?? ""} onChange={(e) => {
          if (e.target.value === "__new") setNewLoc(""); else guard(() => onPatch({ location_id: e.target.value || null }));
        }}>
          <option value="">(tanpa latar)</option>
          {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          <option value="__new">+ Latar baru…</option>
        </select>
        {newLoc !== null && (
          <div className="inline-new">
            <input autoFocus value={newLoc} maxLength={60} placeholder="Nama latar" aria-label="Nama latar baru" onChange={(e) => setNewLoc(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") void createLocation(); if (e.key === "Escape") setNewLoc(null); }} />
            <button className="btn primary sm" disabled={!newLoc.trim()} onClick={() => void createLocation()}>Buat</button>
            <button className="btn ghost sm" onClick={() => setNewLoc(null)} aria-label="Batal"><X size={13} /></button>
          </div>
        )}
        {scene.location?.image_id && <img className="loc-thumb" src={api.imageUrl(scene.location.image_id)} alt={scene.location.name} />}
        <button className="btn ghost sm" onClick={onManageLocations}>Kelola latar & gambarnya</button>
        <label className="field">Waktu / suasana
          <SaveText label="Waktu" value={scene.time_of_day} maxLength={60} list="time-hints" placeholder="senja, hujan gerimis…" onSave={(v) => onPatch({ time_of_day: v })} />
        </label>
        <label className="field">Durasi rencana (detik)
          <SaveText label="Durasi rencana" value={scene.planned_seconds ? String(scene.planned_seconds) : ""} maxLength={3} list="planned-hints" placeholder="mis. 8"
            onSave={(v) => {
              const text = v.trim();
              const n = Number(text);
              if (text && (!Number.isInteger(n) || n < 1 || n > 120)) { toast.error("Durasi rencana 1 sampai 120 detik"); return Promise.reject(new Error("durasi")); }
              return onPatch({ planned_seconds: text ? n : null });
            }} />
        </label>
        <label className="field">Kamera
          <SaveText label="Kamera" value={scene.camera} maxLength={120} list="camera-hints" placeholder="dolly in, orbit…" onSave={(v) => onPatch({ camera: v })} />
        </label>
        <datalist id="planned-hints">{[4, 5, 8, 10].map((n) => <option key={n} value={n} />)}</datalist>
        <datalist id="time-hints">{TIME_HINTS.map((t) => <option key={t} value={t} />)}</datalist>
        <datalist id="camera-hints">{CAMERA_HINTS.map((t) => <option key={t} value={t} />)}</datalist>
      </Section>}

      {!promptMode && <Section title="Pemeran, tampilan, dan aksi">
        <CastEditor key={scene.id} scene={scene} characters={characters} locked={locked} onSave={(cast) => onPatch({ cast })} />
      </Section>}

      {!promptMode && <Section title="Dialog / catatan">
        <SaveText label="Dialog" multiline rows={3} value={scene.dialogue} maxLength={1000} placeholder="Tidak dikirim ke AI; untuk pegangan penulisan"
          onSave={(v) => onPatch({ dialogue: v })} />
        <label className="field">Teks tambahan untuk prompt
          <SaveText label="Teks tambahan" multiline rows={2} value={scene.extra_prompt} maxLength={500} placeholder="detail yang ingin ikut saat generate nanti"
            onSave={(v) => onPatch({ extra_prompt: v })} />
        </label>
      </Section>}

      <Section title="Hasil">
        <div className="take-row">
          {scene.keyframe_image_id ? <img src={api.imageUrl(scene.keyframe_image_id)} alt="Keyframe" /> : <div className="take-empty">Keyframe</div>}
          {scene.clip_id && scene.clip_status === "completed" ? <video src={`${api.clipUrl(scene.clip_id)}#t=0.1`} controls muted playsInline preload="metadata" />
            : <div className="take-empty">{scene.clip_id ? `Video: ${scene.clip_status}` : "Video"}</div>}
        </div>
        <PickGrid title={scene.keyframe_image_id ? "Ganti keyframe dari library" : "Pakai gambar dari library sebagai keyframe"}
          empty={images.length === 0 ? "Library gambar masih kosong." : undefined}>
          {images.slice(0, 60).map((i) => (
            <button key={i.id} className={`thumb ${i.id === scene.keyframe_image_id ? "sel" : ""}`} disabled={locked} aria-label="Pilih keyframe"
              onClick={() => guard(() => onPatch({ keyframe_image_id: i.id }))}><img src={api.imageUrl(i.id)} alt="" loading="lazy" /></button>
          ))}
        </PickGrid>
        <PickGrid title={scene.clip_id ? "Ganti video dari library" : "Pakai video dari library"}
          empty={ready.length === 0 ? "Belum ada video selesai. Buat di halaman Gambar → Video." : undefined}>
          {ready.map((c) => (
            <button key={c.id} className={`thumb ${c.id === scene.clip_id ? "sel" : ""}`} disabled={locked} aria-label={`Pilih video: ${c.prompt}`} title={c.prompt}
              onClick={() => guard(() => onPatch({ clip_id: c.id, ...(scene.keyframe_image_id || !c.source_image_id ? {} : { keyframe_image_id: c.source_image_id }) }))}>
              <video src={`${api.clipUrl(c.id)}#t=0.1`} muted preload="metadata" playsInline />
            </button>
          ))}
        </PickGrid>
        <div className="actions">
          {scene.keyframe_image_id && <button className="btn ghost sm" disabled={locked} onClick={() => guard(() => onPatch({ keyframe_image_id: null }))}>Lepas keyframe</button>}
          {scene.clip_id && <button className="btn ghost sm" disabled={locked} onClick={() => guard(() => onPatch({ clip_id: null }))}>Lepas video</button>}
        </div>
        <Takes scene={scene} locked={locked} onPatch={onPatch} />
      </Section>

      <Section title="Previs 3D (blockout)">
        <p className="muted">Susun manekin, properti, dan kamera bergerak; AI bisa menyusun dari naskah. Hasilnya video previs kasar yang bisa jadi referensi gerak.</p>
        <div className="take-row">
          {scene.blockout_image_id ? <img src={api.imageUrl(scene.blockout_image_id)} alt="Render blockout" /> : <div className="take-empty">Blockout</div>}
          {scene.previs_ref_id ? <video src={api.referenceUrl(scene.previs_ref_id)} controls muted playsInline preload="metadata" /> : <div className="take-empty">Previs</div>}
        </div>
        <button className="btn block" onClick={() => setBlockoutOpen(true)}><Box size={15} /> {scene.blockout ? "Buka susunan 3D" : "Susun adegan 3D"}</button>
        {scene.previs_ref_id && (
          <details className="pick"><summary>Buat video dari previs</summary><PrevisVideoPanel scene={scene} locked={locked} onDone={onGenerated} /></details>
        )}
        {blockoutOpen && (
          <Suspense fallback={null}>
            <Blockout scene={scene} aspect={aspect} onClose={() => setBlockoutOpen(false)} onSaved={onGenerated} />
          </Suspense>
        )}
      </Section>

      {!promptMode && <Section title="Buat keyframe">
        <KeyframePanel scene={scene} locked={locked} onDone={onGenerated} />
      </Section>}

      {!promptMode && <Section title="Buat video">
        <VideoPanel scene={scene} locked={locked} onDone={onGenerated} />
      </Section>}

      <div className="actions del">
        {confirmDel ? (
          <>
            <button className="btn danger" onClick={onDelete}><Trash2 size={14} /> Ya, hapus adegan</button>
            <button className="btn ghost" onClick={() => setConfirmDel(false)}>Batal</button>
            <span className="muted">Gambar dan video tetap di library.</span>
          </>
        ) : <button className="btn ghost danger" disabled={locked} onClick={() => setConfirmDel(true)}><Trash2 size={14} /> Hapus adegan</button>}
      </div>
    </>
  );
}
