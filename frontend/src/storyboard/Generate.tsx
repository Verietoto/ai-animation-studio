import { useEffect, useRef, useState } from "react";
import { ImageIcon, Sparkles, Video } from "lucide-react";
import { api, EstimateRequest, Location, Scene, SceneUpdate } from "../api";
import { ModelParams, useAsync, VideoParams } from "../components";
import { ModelPicker } from "../catalog";
import { EstimateLine, useConfirmedRun, useEstimate } from "../estimate";
import { useTrack } from "../queue";

/** Model bawaan keyframe/latar: terbaik per harga di spike plan 08 (tokoh jelas, rasio bisa dikirim). */
export const DEFAULT_IMAGE_MODEL = "bytedance-seed/seedream-5-0-flash";

/** `v` hanya membuat estimasi dihitung ulang saat adegan berubah (mis. pemeran); server mengabaikannya. */
type Body = EstimateRequest & { v?: string };

/** Keyframe adegan dari latar + pemeran + tampilan; satu panggilan, dialog biaya wajib. */
export function KeyframePanel({ scene, locked, onDone }: { scene: Scene; locked: boolean; onDone: () => void }) {
  const [model, setModel] = useState(DEFAULT_IMAGE_MODEL);
  const track = useTrack();
  const body: Body | null = model ? { kind: "scene_keyframe", model, scene_id: scene.id, v: scene.updated_at } : null;
  const live = useEstimate(body);
  const runner = useConfirmedRun(() => body, async (c) => {
    await track(`Keyframe adegan ${scene.number}`, () => api.sceneKeyframe(scene.id, { model, ...c }));
    onDone();
  });
  return (
    <div className="gen">
      <ModelPicker kind="image" label="Model keyframe" value={model} onChange={setModel} />
      <EstimateLine est={live.est} error={live.error} />
      {runner.error && <p className="error">{runner.error}</p>}
      <button className="btn primary block" disabled={locked || !!live.error || !live.est || !!live.est.blocked} onClick={() => void runner.start()}>
        <ImageIcon size={15} /> {scene.keyframe_image_id ? "Buat keyframe lagi (take baru)" : "Buat keyframe"}
      </button>
      <p className="muted">Gambar 1 = latar, lalu satu gambar per pemeran{live.est?.inputs ? ` (${live.est.inputs} gambar dikirim)` : ""}. Hasil baru jadi take; yang terpilih tidak diganti.</p>
      {runner.dialog}
    </div>
  );
}

const nearest = (options: number[], want: number) => options.reduce((a, b) => (Math.abs(b - want) < Math.abs(a - want) ? b : a));

/** Video adegan dari keyframe terpilih; durasi bawaan mengikuti rencana detik (dibulatkan ke yang didukung model). */
export function VideoPanel({ scene, locked, onDone }: { scene: Scene; locked: boolean; onDone: () => void }) {
  const models = useAsync(api.videoModels, []);
  const [model, setModel] = useState("");
  const [params, setParams] = useState<VideoParams>({ generate_audio: false });
  const key = useRef(crypto.randomUUID());   // satu kunci per percobaan; klik ganda tidak membuat job ganda
  const info = (models.data ?? []).find((m) => m.id === model);
  const planned = scene.planned_seconds;

  useEffect(() => {   // durasi bawaan = rencana, dibulatkan ke durasi yang didukung model
    const options = info?.supported_durations;
    if (options?.length && planned && params.duration === undefined) setParams((p) => ({ ...p, duration: nearest(options, planned) }));
  }, [info, planned, params.duration]);

  const body: Body | null = model && scene.keyframe_image_id
    ? { kind: "scene_video", model, scene_id: scene.id, duration: params.duration, resolution: params.resolution,
        aspect_ratio: params.aspect_ratio, generate_audio: params.generate_audio, v: scene.updated_at } : null;
  const live = useEstimate(body);
  const runner = useConfirmedRun(() => body, async (c) => {
    await api.sceneVideo(scene.id, { model, duration: params.duration, resolution: params.resolution, aspect_ratio: params.aspect_ratio,
      generate_audio: params.generate_audio, idempotency_key: key.current, ...c });
    key.current = crypto.randomUUID();
    onDone();
  });
  const off = planned && params.duration && params.duration !== planned;

  if (!scene.keyframe_image_id) return <p className="muted">Buat atau pilih keyframe dulu, lalu video bisa dibuat dari sini.</p>;
  return (
    <div className="gen">
      {models.error ? <p className="error">{models.error}</p> :
        <ModelParams models={models.data ?? []} model={model} setModel={setModel} params={params} setParams={setParams} />}
      {off ? <p className="warn">Rencana {planned} detik, model memberi {params.duration} detik.</p> : null}
      <EstimateLine est={live.est} error={live.error} />
      {runner.error && <p className="error">{runner.error}</p>}
      <button className="btn primary block" disabled={locked || !model || !live.est || !!live.est.blocked} onClick={() => void runner.start()}>
        <Video size={15} /> {scene.clip_id ? "Buat video lagi (take baru)" : "Buat video"}
      </button>
      {runner.dialog}
    </div>
  );
}

/** Gambar latar dari deskripsi (teks ke gambar, tanpa gambar input). */
export function LocationImagePanel({ loc, onDone }: { loc: Location; onDone: () => void }) {
  const [model, setModel] = useState(DEFAULT_IMAGE_MODEL);
  const track = useTrack();
  const body: Body | null = model ? { kind: "location_image", model, location_id: loc.id, v: `${loc.name}|${loc.description}` } : null;
  const live = useEstimate(body);
  const runner = useConfirmedRun(() => body, async (c) => {
    await track(`Gambar latar: ${loc.name}`, () => api.locationImage(loc.id, { model, ...c }));
    onDone();
  });
  return (
    <div className="gen">
      <ModelPicker kind="image" label="Model gambar latar" value={model} onChange={setModel} />
      <EstimateLine est={live.est} error={live.error} />
      {runner.error && <p className="error">{runner.error}</p>}
      <button className="btn" disabled={!!live.error || !live.est || !!live.est.blocked} onClick={() => void runner.start()}>
        <Sparkles size={14} /> {loc.image_id ? "Buat ulang dari deskripsi" : "Buat dari deskripsi"}
      </button>
      <p className="muted">Memakai nama dan deskripsi latar. Gambar lama tetap di library.</p>
      {runner.dialog}
    </div>
  );
}

/** Semua hasil generate adegan ini; klik untuk memilih yang dipakai. */
export function Takes({ scene, locked, onPatch }: { scene: Scene; locked: boolean; onPatch: (body: SceneUpdate) => Promise<unknown> }) {
  if (scene.keyframe_takes.length <= 1 && scene.video_takes.length <= 1) return null;
  const pick = (body: SceneUpdate) => void onPatch(body).catch(() => {});
  return (
    <div className="takes">
      {scene.keyframe_takes.length > 1 && <>
        <span className="muted">Take keyframe</span>
        <div className="pick-grid">{scene.keyframe_takes.map((id) => (
          <button key={id} className={`thumb ${id === scene.keyframe_image_id ? "sel" : ""}`} disabled={locked} aria-label="Pilih take keyframe"
            onClick={() => pick({ keyframe_image_id: id })}><img src={api.imageUrl(id)} alt="" loading="lazy" /></button>
        ))}</div>
      </>}
      {scene.video_takes.length > 1 && <>
        <span className="muted">Take video</span>
        <div className="pick-grid">{scene.video_takes.map((t) => (
          <button key={t.id} className={`thumb ${t.id === scene.clip_id ? "sel" : ""}`} disabled={locked} aria-label={`Pilih take video (${t.status})`}
            onClick={() => pick({ clip_id: t.id })}>
            {t.status === "completed" ? <video src={`${api.clipUrl(t.id)}#t=0.1`} muted preload="metadata" playsInline /> : <span className="tag">{t.status}</span>}
          </button>
        ))}</div>
      </>}
    </div>
  );
}

/** Video adegan dari previs 3D (Seedance reference, plan 15): video previs untuk gerak/kamera + gambar pemeran dan latar. */
export function PrevisVideoPanel({ scene, locked, onDone }: { scene: Scene; locked: boolean; onDone: () => void }) {
  const models = useAsync(api.videoModels, []);
  const list = (models.data ?? []).filter((m) => m.id.startsWith("bytedance/seedance-2"));
  const [model, setModel] = useState("");
  const [params, setParams] = useState<VideoParams>({ generate_audio: false });
  const key = useRef(crypto.randomUUID());
  const info = list.find((m) => m.id === model);
  const want = scene.blockout?.duration ?? scene.planned_seconds;

  useEffect(() => { if (!model && list.length) setModel((list.find((m) => m.id.endsWith("seedance-2.0-mini")) ?? list[0]).id); }, [list, model]);
  useEffect(() => {   // bawaan: resolusi terendah (paling murah) dan durasi sedekat mungkin dengan previs
    if (!info) return;
    setParams((p) => ({
      ...p, resolution: p.resolution ?? info.supported_resolutions?.[0],
      duration: p.duration ?? (info.supported_durations?.length && want ? nearest(info.supported_durations, want) : undefined),
    }));
  }, [info, want]);

  const body: Body | null = model
    ? { kind: "scene_previs_video", model, scene_id: scene.id, duration: params.duration, resolution: params.resolution,
        aspect_ratio: params.aspect_ratio, generate_audio: params.generate_audio, v: scene.updated_at } : null;
  const live = useEstimate(body);
  const runner = useConfirmedRun(() => body, async (c) => {
    await api.scenePrevisVideo(scene.id, { model, duration: params.duration, resolution: params.resolution, aspect_ratio: params.aspect_ratio,
      generate_audio: params.generate_audio, idempotency_key: key.current, ...c });
    key.current = crypto.randomUUID();
    onDone();
  });
  return (
    <div className="gen">
      <p className="muted">Mengirim video previs + gambar pemeran dan latar ke Seedance. Cocok untuk gaya kartun (orang foto-realistik ditolak) dan butuh hosting publik (tunnel/S3).</p>
      {models.error ? <p className="error">{models.error}</p> :
        <ModelParams models={list} model={model} setModel={setModel} params={params} setParams={setParams} />}
      <EstimateLine est={live.est} error={live.error} />
      {runner.error && <p className="error">{runner.error}</p>}
      <button className="btn primary block" disabled={locked || !model || !!live.error || !live.est || !!live.est.blocked} onClick={() => void runner.start()}>
        <Video size={15} /> Buat video dari previs
      </button>
      {runner.dialog}
    </div>
  );
}
