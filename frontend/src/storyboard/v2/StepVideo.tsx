// Langkah "Video" Storyboard v2 (plan 18 fase D): tiap adegan dikirim ke Seedance 2.0 sebagai satu video dengan referensi bernomor
// (@Image N = keyframe beat, karakter, latar; @Audio N = suara). Pratinjau menunjukkan PERSIS apa yang dikirim; prompt boleh disunting.
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2, Mic, Video } from "lucide-react";
import { toast } from "sonner";
import { api, Character, EstimateRequest, FilmDetail, Location, ProjectSettings, Scene, StoryboardPreview } from "../../api";
import { EstimateLine, useConfirmedRun, useEstimate } from "../../estimate";
import { TimelineView, STATUS_LABEL } from "../Views";
import { useBatch } from "../journey/batch";
import { ScenePromptEditor } from "./ScenePrompt";

const secondsOf = (s: Scene, beatEnd: number | null) => beatEnd ?? s.planned_seconds ?? null;

function ScenePanel({ scene, settings, characters, locations, locked, onSaved, onDone }: {
  scene: Scene; settings: ProjectSettings; characters: Character[]; locations: Location[]; locked: boolean; onSaved: () => void; onDone: () => void;
}) {
  const [pv, setPv] = useState<StoryboardPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [chainBusy, setChainBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    setPv(null); setError(null);
    api.storyboardPreview(scene.id, false)
      .then((r) => { if (alive) setPv(r); })
      .catch((e: Error) => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [scene.id, scene.updated_at, settings.video_model, settings.video_resolution, settings.aspect_ratio, settings.generate_audio, settings.style]);

  const body: EstimateRequest | null = pv && !dirty ? { kind: "storyboard_video", model: pv.model, scene_id: scene.id } : null;
  const live = useEstimate(body);
  const run = useConfirmedRun(() => body, async (c) => {
    await api.storyboardVideo(scene.id, { use_previs: false, idempotency_key: crypto.randomUUID(), ...c });   // prompt = prompt adegan yang tersimpan
    toast.success("Video dikirim ke Seedance; hasilnya muncul di antrian dan adegan ini");
    onDone();
  });

  const editor = <ScenePromptEditor scene={scene} characters={characters} locations={locations} locked={locked} rows={11} onSaved={onSaved} onDirty={setDirty} />;
  if (error) return <div className="v2-vid"><p className="error v2-vid-error"><AlertTriangle size={14} /> {error}</p>{editor}</div>;
  if (!pv) return <p className="muted"><Loader2 size={14} className="spin" /> Menyiapkan pratinjau…</p>;
  const images = pv.refs.filter((r) => r.kind === "image");
  async function setChain(on: boolean) {
    setChainBusy(true);
    try { await api.updateScene(scene.id, { start_from_prev: on }); onSaved(); }
    catch (e) { toast.error((e as Error).message); }
    finally { setChainBusy(false); }
  }
  return (
    <div className="v2-vid">
      <div className="chips">
        <span className="chip"><b>{pv.duration}</b> dtk</span>
        <span className="chip">{pv.model.split("/").pop()}</span>
        <span className="chip">{pv.resolution}</span>
        <span className="chip">{pv.aspect_ratio}</span>
        <span className="chip">{pv.generate_audio ? "dengan suara" : "tanpa suara"}</span>
      </div>

      {editor}

      {scene.number > 1 && (
        <label className="check v2-chain">
          <input type="checkbox" checked={scene.start_from_prev} disabled={locked || chainBusy || (!scene.start_from_prev && !pv.can_start_from_prev.ok)}
            onChange={(e) => void setChain(e.target.checked)} />
          Mulai dari frame akhir adegan sebelumnya
          {!pv.can_start_from_prev.ok && <span className="warn"> ({pv.can_start_from_prev.reason})</span>}
        </label>
      )}
      {pv.start_frame && (
        <div className="v2-startframe">
          <video src={`${api.clipUrl(pv.start_frame.clip_id)}#t=0.1`} muted preload="metadata" playsInline
            onLoadedMetadata={(e) => { const v = e.currentTarget; if (v.duration) v.currentTime = Math.max(0, v.duration - 0.05); }} />
          <div><b>Frame awal</b><span className="muted"> frame akhir video adegan {pv.start_frame.scene_number}</span>
            <p className="muted">Mode ini tidak mengirim gambar karakter, latar, atau sampel suara; wajah dan tempat mengikuti frame awal.</p></div>
        </div>
      )}

      <div className="field">Aset yang dikirim ({pv.refs.length})
        {pv.refs.length === 0 && <span className="muted">Tidak ada gambar. Sebut karakter atau latar bergambar di prompt.</span>}
        {pv.start_frame && <span className="muted">Hanya frame awal yang dikirim.</span>}
        <ol className="v2-refs">
          {images.map((r) => (
            <li key={`i${r.n}`}><img src={api.imageUrl(r.image_id!)} alt="" loading="lazy" /><b>@image_{r.n}</b><span className="muted clamp1">{r.label}</span></li>
          ))}
          {pv.refs.filter((r) => r.kind === "audio").map((r) => (
            <li key={`a${r.n}`} className="aud"><span className="v2-ref-ico"><Mic size={16} /></span><b>@audio_{r.n}</b><span className="muted clamp1">{r.label}</span></li>
          ))}
        </ol>
      </div>
      {!pv.public_media && <p className="muted">Hosting publik tidak aktif: sampel suara tidak dikirim; model memilih suaranya dari deskripsi dialog.</p>}
      {pv.warnings.length > 0 && <ul className="v2-warns">{pv.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}

      <details className="v2-sent">
        <summary>Teks yang persis dikirim ke Seedance</summary>
        <pre>{pv.prompt}</pre>
      </details>

      <EstimateLine est={live.est} error={live.error} />
      {run.error && <p className="error">{run.error}</p>}
      {dirty && <p className="warn">Simpan prompt adegan dulu; video dibuat dari prompt yang tersimpan.</p>}
      <button className="btn primary" disabled={locked || dirty || !!live.error || !live.est} onClick={() => void run.start()}>
        <Video size={14} /> {scene.clip_id ? "Buat take video baru" : "Buat video"}
      </button>
      <p className="muted">Biaya dikonfirmasi dulu. Storyboard v2 tidak dibatasi batas per job atau harian.</p>
      {run.dialog}
    </div>
  );
}

export function StepVideo({ detail, settings, characters, locations, locked, reload, onGenerated, onRender, goStep }: {
  detail: FilmDetail; settings: ProjectSettings | null; characters: Character[]; locations: Location[]; locked: boolean; reload: () => Promise<unknown>; onGenerated: () => void;
  onRender: () => void; goStep: (n: number) => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [beatEnds, setBeatEnds] = useState<Record<string, number | null>>({});
  const ids = detail.scenes.map((s) => s.id).join(",");
  useEffect(() => {
    let alive = true;
    void Promise.all(detail.scenes.map((s) => api.beats(s.id).then((r) => [s.id, r.beats.length ? r.beats[r.beats.length - 1].end : null] as const).catch(() => [s.id, null] as const)))
      .then((all) => { if (alive) setBeatEnds(Object.fromEntries(all)); });
    return () => { alive = false; };
  }, [ids]);   // eslint-disable-line react-hooks/exhaustive-deps

  const after = () => { void reload(); onGenerated(); };
  const batch = useBatch("Buat semua video", "Satu video per adegan yang belum punya video (atau videonya gagal), dengan pengaturan proyek. Hasilnya take baru.", after);
  const need = useMemo(() => detail.scenes.filter((s) => !s.clip_id || s.status === "gagal"), [detail.scenes]);
  const tooLong = (s: Scene) => (secondsOf(s, beatEnds[s.id] ?? null) ?? 0) > 15;
  // adegan berantai (frame awal dari adegan sebelumnya) hanya jalan bila video adegan sebelumnya SUDAH selesai
  const waitingFor = (s: Scene): number | null => {
    if (!s.start_from_prev) return null;
    const prev = detail.scenes[detail.scenes.findIndex((x) => x.id === s.id) - 1];
    return prev && prev.clip_id && prev.clip_status === "completed" ? null : (prev?.number ?? null);
  };
  const runnable = need.filter((s) => !tooLong(s) && waitingFor(s) === null);
  const waiting = need.filter((s) => !tooLong(s) && waitingFor(s) !== null);

  const all = () => void batch.start(runnable.map((s) => ({
    label: `Adegan ${s.number}`,
    estimate: { kind: "storyboard_video" as const, model: settings?.video_model ?? "", scene_id: s.id },
    run: (c: { confirmed_cost: number | null; accept_unknown_cost: boolean }) => api.storyboardVideo(s.id, { idempotency_key: crypto.randomUUID(), ...c }),
  })));

  if (!settings) return <p className="muted"><Loader2 size={14} className="spin" /> Memuat pengaturan proyek…</p>;
  return (
    <div className="jr-produce">
      <div className="jr-card">
        <h3>Video dengan Seedance</h3>
        <p className="muted">Tiap adegan dikirim sebagai satu video (4 sampai 15 detik) dari prompt adegannya, dengan gambar karakter dan latar yang disebut di prompt (serta suara penutur) sebagai referensi. Pengaturan: {settings.video_model.split("/").pop()}, {settings.video_resolution}, {settings.aspect_ratio}, {settings.generate_audio ? "dengan suara" : "tanpa suara"}.
          {" "}<button className="btn ghost sm" onClick={() => goStep(1)}>Ubah di pengaturan proyek</button></p>
        <button className="btn primary" disabled={locked || batch.busy || runnable.length === 0} onClick={all}>
          <Video size={14} /> Buat semua video yang belum ada ({runnable.length})
        </button>
        {waiting.length > 0 && <p className="muted">{waiting.length} adegan berantai menunggu video adegan sebelumnya selesai ({waiting.map((s) => `${s.number} menunggu ${waitingFor(s)}`).join(", ")}); jalankan lagi setelah selesai.</p>}
        {need.length - waiting.length > runnable.length && <p className="warn"><AlertTriangle size={13} /> {need.length - waiting.length - runnable.length} adegan lebih dari 15 detik: bagi jadi beberapa adegan dulu.</p>}
        {batch.dialog}
      </div>

      <ul className="jr-rows">
        {detail.scenes.map((s) => {
          const sec = secondsOf(s, beatEnds[s.id] ?? null);
          return (
            <li key={s.id} className="jr-row v2-vrow">
              <div className="v2-vrow-head">
                <div className="jr-thumb">
                  {s.clip_id && s.clip_status === "completed" ? <video src={`${api.clipUrl(s.clip_id)}#t=0.1`} muted preload="metadata" playsInline />
                    : s.location?.image_id ? <img src={api.imageUrl(s.location.image_id)} alt="" loading="lazy" /> : <Video size={20} />}
                </div>
                <div className="jr-grow">
                  <strong>Adegan {s.number}</strong> <span className={`pill st-${s.status}`}>{STATUS_LABEL[s.status]}</span>
                  <div className="muted clamp1">{s.location?.name ?? "tanpa latar"} · {s.cast.map((c) => c.character_name).join(", ") || "tanpa pemeran"} · {sec != null ? `${sec} dtk` : "durasi belum diatur"}</div>
                  {s.start_from_prev && <div className="muted">berantai dari frame akhir adegan {s.number - 1}</div>}
                  {tooLong(s) && <div className="warn"><AlertTriangle size={12} /> Lebih dari 15 detik; bagi adegan ini.</div>}
                </div>
                <button className="btn sm" disabled={locked} onClick={() => setOpen(open === s.id ? null : s.id)} aria-expanded={open === s.id}>
                  {open === s.id ? "Tutup" : s.clip_id ? "Take baru…" : "Siapkan video…"}
                </button>
              </div>
              {s.clip_id && s.clip_status === "completed" && <video className="v2-vplay" src={api.clipUrl(s.clip_id)} controls preload="metadata" playsInline />}
              {open === s.id && <ScenePanel scene={s} settings={settings} characters={characters} locations={locations} locked={locked} onSaved={() => void reload()} onDone={() => { setOpen(null); after(); }} />}
            </li>
          );
        })}
      </ul>

      <div className="jr-card">
        <h3>Render episode</h3>
        <TimelineView detail={detail} rendering={locked} onRender={onRender} />
      </div>
    </div>
  );
}
