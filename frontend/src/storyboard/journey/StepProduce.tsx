// Langkah 5 alur episode: animasi sesungguhnya (keyframe, video, video dari previs) dan render episode (plan 15 fase C).
import { useEffect, useState } from "react";
import { ImageIcon, Video } from "lucide-react";
import { api, FilmDetail, JourneyState } from "../../api";
import { ModelParams, useAsync, VideoParams } from "../../components";
import { ModelPicker } from "../../catalog";
import { DEFAULT_IMAGE_MODEL, PrevisVideoPanel } from "../Generate";
import { STATUS_LABEL, TimelineView } from "../Views";
import { useBatch } from "./batch";

const nearest = (options: number[], want: number) => options.reduce((a, b) => (Math.abs(b - want) < Math.abs(a - want) ? b : a));

export function StepProduce({ detail, journey, locked, reload, onGenerated, onSelect, onRender }: {
  detail: FilmDetail; journey: JourneyState; locked: boolean; reload: () => Promise<unknown>; onGenerated: () => void;
  onSelect: (id: string) => void; onRender: () => void;
}) {
  const scenes = detail.scenes;
  const p = journey.progress;
  const after = () => { void reload(); onGenerated(); };
  const models = useAsync(api.videoModels, []);
  const [imgModel, setImgModel] = useState(DEFAULT_IMAGE_MODEL);
  const [vModel, setVModel] = useState("");
  const [vParams, setVParams] = useState<VideoParams>({ generate_audio: false });
  const info = (models.data ?? []).find((m) => m.id === vModel);

  useEffect(() => { setVParams((x) => ({ ...x, duration: undefined })); }, [vModel]);   // durasi per adegan mengikuti rencananya, kecuali dipilih

  const kfBatch = useBatch("Buat semua keyframe", "Satu keyframe per adegan yang belum punya. Hasilnya jadi take; yang sudah terpilih tidak diganti.", after);
  const vBatch = useBatch("Buat semua video", "Satu video per adegan yang punya keyframe tetapi belum punya video (atau videonya gagal). Durasi mengikuti rencana adegan.", after);

  const needKeyframe = scenes.filter((s) => !s.keyframe_image_id);
  const needVideo = scenes.filter((s) => s.keyframe_image_id && (!s.clip_id || s.status === "gagal"));
  const durationFor = (planned: number | null) => vParams.duration ?? (info?.supported_durations?.length && planned ? nearest(info.supported_durations, planned) : undefined);

  const keyframes = () => void kfBatch.start(needKeyframe.map((s) => ({
    label: `Adegan ${s.number}`,
    estimate: { kind: "scene_keyframe" as const, model: imgModel, scene_id: s.id },
    run: (c: { confirmed_cost: number | null; accept_unknown_cost: boolean }) => api.sceneKeyframe(s.id, { model: imgModel, ...c }),
  })));
  const videos = () => void vBatch.start(needVideo.map((s) => {
    const body = { model: vModel, duration: durationFor(s.planned_seconds), resolution: vParams.resolution, aspect_ratio: vParams.aspect_ratio, generate_audio: vParams.generate_audio };
    return {
      label: `Adegan ${s.number}`,
      estimate: { kind: "scene_video" as const, scene_id: s.id, ...body },
      run: (c: { confirmed_cost: number | null; accept_unknown_cost: boolean }) => api.sceneVideo(s.id, { ...body, idempotency_key: crypto.randomUUID(), ...c }),
    };
  }));
  const busy = kfBatch.busy || vBatch.busy;

  return (
    <div className="jr-produce">
      <div className="jr-card">
        <h3>Ringkasan produksi</h3>
        <div className="chips">
          <span className="chip"><b>{p.keyframe}/{p.scenes}</b> keyframe</span>
          <span className="chip"><b>{p.video_ready}/{p.scenes}</b> video selesai</span>
          {p.previs > 0 && <span className="chip"><b>{p.previs}</b> previs</span>}
          {p.rendered && <span className="chip">episode sudah dirender</span>}
        </div>
        <div className="jr-batch">
          <div>
            <ModelPicker kind="image" label="Model keyframe" value={imgModel} onChange={setImgModel} />
            <button className="btn primary block" disabled={locked || busy || needKeyframe.length === 0} onClick={keyframes}>
              <ImageIcon size={14} /> Buat semua keyframe yang belum ada ({needKeyframe.length})
            </button>
          </div>
          <div>
            {models.error ? <p className="error">{models.error}</p> :
              <ModelParams models={models.data ?? []} model={vModel} setModel={setVModel} params={vParams} setParams={setVParams} />}
            <button className="btn primary block" disabled={locked || busy || !vModel || needVideo.length === 0} onClick={videos}>
              <Video size={14} /> Buat semua video yang belum ada ({needVideo.length})
            </button>
          </div>
        </div>
        <p className="muted">Setiap tombol meminta satu konfirmasi untuk total biaya, lalu mengerjakan adegan satu per satu dan berhenti bila ada yang gagal atau batas biaya tercapai.</p>
        {kfBatch.dialog}{vBatch.dialog}
      </div>

      <ul className="jr-rows">
        {scenes.map((s) => (
          <li key={s.id} className="jr-row">
            <div className="jr-thumb">{s.keyframe_image_id ? <img src={api.imageUrl(s.keyframe_image_id)} alt="" loading="lazy" /> : <ImageIcon size={20} />}</div>
            <div className="jr-grow">
              <strong>Adegan {s.number}</strong> <span className={`pill st-${s.status}`}>{STATUS_LABEL[s.status]}</span>
              <div className="muted clamp1">{s.location?.name ?? "tanpa latar"} · {s.cast.map((c) => c.character_name).join(", ") || "tanpa pemeran"} · {s.planned_seconds ?? "?"} dtk</div>
              {s.previs_ref_id && (
                <details className="pick"><summary>Video dari previs</summary><PrevisVideoPanel scene={s} locked={locked} onDone={after} /></details>
              )}
            </div>
            <button className="btn sm" onClick={() => onSelect(s.id)}>Buka</button>
          </li>
        ))}
      </ul>

      <div className="jr-card">
        <h3>Render episode</h3>
        <TimelineView detail={detail} rendering={locked} onRender={onRender} />
      </div>
    </div>
  );
}
