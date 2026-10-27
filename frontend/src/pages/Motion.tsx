import { useEffect, useRef, useState } from "react";
import { Footprints, Loader2, Scissors, Sparkles, Upload } from "lucide-react";
import { api, Character, Clip, Img, MotionMode, Reference } from "../api";
import { AssetStrip, ModelParams, useAsync, VideoParams } from "../components";
import { ModelPicker } from "../catalog";
import { EstimateLine, useConfirmedRun, useEstimate } from "../estimate";
import { EmptyState, Section, Stage } from "../ui";

/** Tiru gerakan (plan 03, UI plan 09). Model dan label mengikuti hasil spike docs/implementation/03-motion-transfer-spike.md. */
const MODES: { id: MotionMode; title: string; hint: string; model: string }[] = [
  { id: "flux_edit", title: "Ganti subjek (murah)", model: "black-forest-labs/flux-video-edit",
    hint: "±$0,03/detik. Gerakan, kamera, latar, dan suara persis video; wajah karakter hanya perkiraan dari deskripsinya." },
  { id: "anchor_edit", title: "Kunci karakter (mahal)", model: "runway/aleph-2",
    hint: "$0,28/detik, minimal $0,56. Paling mirip karakter: buat anchor frame dulu, lalu video. Batas per job $1 ≈ referensi ≤ 3 detik." },
  { id: "reference", title: "Animasikan gambar (kartun)", model: "bytedance/seedance-2.0-mini",
    hint: "Seedance: karakter dari gambar bergerak meniru video. Hanya kartun/ilustrasi; orang foto-realistik ditolak. Gerakan mirip, tidak persis." },
];
const SEEDANCE = ["bytedance/seedance-2.0-mini", "bytedance/seedance-2.0-fast", "bytedance/seedance-2.0", "bytedance/seedance-2.5"];
const PROMPTS: Record<MotionMode, string> = {
  flux_edit: "Replace the person in the video with the new subject. Keep the exact motion, timing, camera and background unchanged.",
  anchor_edit: "Keep the exact motion, timing and camera of the video. The person must look exactly like the keyframe: same face, hairstyle and clothing.",
  reference: "The character in the reference image performs exactly the same movements as the person in video 1, with the same timing and camera framing.",
};
const STALE_MS = 20 * 3600 * 1000;   // URL klip OpenRouter kedaluwarsa ±24 jam (grill 09)

/** Potong rentang video referensi (plan 11). Pratinjau berputar hanya di rentang terpilih. */
function TrimPanel({ refr, max, canTrim, matchSeconds, videoRef, onTrimmed }: {
  refr: Reference; max: number; canTrim: boolean; matchSeconds: number | null;
  videoRef: React.RefObject<HTMLVideoElement>; onTrimmed: (r: Reference) => void;
}) {
  const full = Math.round(refr.duration * 10) / 10;
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(Math.min(full, max));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setStart(0); setEnd(Math.min(full, max)); setError(null); }, [refr.id, full, max]);
  const len = Math.round((end - start) * 10) / 10;
  const bad = len < 1 || len > max + 0.01;
  const unchanged = start === 0 && end >= full;

  useEffect(() => {   // pratinjau berputar di dalam rentang
    const v = videoRef.current;
    if (!v) return;
    const tick = () => { if (v.currentTime >= end || v.currentTime < start - 0.3) v.currentTime = start; };
    v.addEventListener("timeupdate", tick);
    v.currentTime = start;
    return () => v.removeEventListener("timeupdate", tick);
  }, [videoRef, refr.id, start, end]);

  const setS = (s: number) => { setStart(s); if (end - s < 1) setEnd(Math.min(full, s + 1)); if (end - s > max) setEnd(Math.round((s + max) * 10) / 10); };
  const setE = (e: number) => { setEnd(e); if (e - start < 1) setStart(Math.max(0, e - 1)); if (e - start > max) setStart(Math.round((e - max) * 10) / 10); };
  function match() { if (matchSeconds) { const e = Math.min(full, Math.round((start + matchSeconds) * 10) / 10); setEnd(e); setStart(Math.max(0, Math.round((e - Math.min(matchSeconds, max)) * 10) / 10)); } }
  async function cut() {
    setBusy(true); setError(null);
    try { onTrimmed(await api.trimReference(refr.id, start, end)); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return (
    <Section title="Potong video referensi">
      {full > max && <p className="warn">Video {full} dtk; yang dipakai maksimal {max} dtk. Pilih bagiannya lalu Potong.</p>}
      <label className="field">Mulai: {start.toFixed(1)} dtk
        <input type="range" min={0} max={full} step={0.1} value={start} onChange={(e) => setS(Number(e.target.value))} aria-label="Mulai" /></label>
      <label className="field">Akhir: {end.toFixed(1)} dtk
        <input type="range" min={0} max={full} step={0.1} value={end} onChange={(e) => setE(Number(e.target.value))} aria-label="Akhir" /></label>
      <p className="mono">Panjang hasil {len.toFixed(1)} dtk{bad ? ` (harus 1–${max} dtk)` : ""}</p>
      <div className="actions">
        {matchSeconds != null && <button className="btn" onClick={match}>Samakan dengan durasi video ({matchSeconds} dtk)</button>}
        <button className="btn primary" disabled={busy || bad || !canTrim || unchanged} onClick={() => void cut()}>
          {busy ? <Loader2 size={14} className="spin" /> : <Scissors size={14} />} Potong
        </button>
      </div>
      {!canTrim && <p className="muted">Memotong klip library membuat berkas baru yang harus bisa diunduh model: isi PUBLIC_TUNNEL=cloudflared atau S3/R2 di .env, lalu restart backend. Unggahan tetap bisa dipotong.</p>}
      {error && <p className="error">{error}</p>}
    </Section>
  );
}

export default function Motion({ clips, images, characters, addImage, publicMedia, maxReference, onCreated }: {
  clips: Clip[]; images: Img[]; characters: Character[]; addImage: (i: Img) => void; publicMedia: boolean; maxReference: number; onCreated: () => void;
}) {
  const previewRef = useRef<HTMLVideoElement>(null);
  const [ref, setRef] = useState<Reference | null>(null);
  const [refBusy, setRefBusy] = useState(false);
  const [refError, setRefError] = useState<string | null>(null);
  const [mode, setMode] = useState<MotionMode>("flux_edit");
  const [characterId, setCharacterId] = useState("");
  const [subject, setSubject] = useState<string | null>(null);
  const [prompt, setPrompt] = useState(PROMPTS.flux_edit);
  const [anchor, setAnchor] = useState<Img | null>(null);
  const [anchorModel, setAnchorModel] = useState("openai/gpt-image-2");
  const seedance = useAsync(api.videoModels, []);
  const [seedModel, setSeedModel] = useState("bytedance/seedance-2.0-mini");
  const [params, setParams] = useState<VideoParams>({ generate_audio: false, resolution: "480p", duration: 4 });
  const key = useRef(crypto.randomUUID());
  const fileInput = useRef<HTMLInputElement>(null);
  const done = clips.filter((c) => c.status === "completed" && c.has_file);
  const saved = useAsync(api.references, [ref?.id]);   // unggahan, hasil potong, dan previs adegan (bukan dari klip library)
  const own = (saved.data ?? []).filter((r) => !r.source_clip_id);
  const info = MODES.find((m) => m.id === mode)!;
  const characterDesc = characters.find((c) => c.id === characterId)?.description ?? "";
  const [subjectText, setSubjectText] = useState("");   // teks subjek untuk FLUX; diisi dari deskripsi karakter, boleh diedit
  useEffect(() => { setSubjectText(characterDesc); }, [characterId, characterDesc]);
  const model = mode === "reference" ? seedModel : info.model;

  function pickMode(m: MotionMode) {
    if (prompt === PROMPTS[mode]) setPrompt(PROMPTS[m]);   // hanya ganti template bila user belum mengubahnya
    setMode(m);
  }
  async function loadRef(load: () => Promise<Reference>) {
    setRefBusy(true); setRefError(null);
    try { setRef(await load()); setAnchor(null); } catch (e) { setRefError((e as Error).message); } finally { setRefBusy(false); }
  }

  const missing = !ref ? "Pilih video referensi dulu." : mode === "anchor_edit" && !characterId ? "Pilih karakter."
    : mode === "anchor_edit" && !anchor ? "Buat anchor frame dulu." : mode === "reference" && !characterId && !subject ? "Pilih karakter atau gambar subjek." : null;
  const estBody = ref ? { kind: "motion" as const, mode, model, reference_id: ref.id,
    ...(mode === "reference" ? params : {}) } : null;
  const live = useEstimate(estBody);
  const runner = useConfirmedRun(() => estBody, async (c) => {
    await api.motion({ mode, model, reference_id: ref!.id, prompt, character_id: characterId || undefined,
      subject_text: mode === "flux_edit" && subjectText.trim() ? subjectText.trim() : undefined,
      image_ids: mode === "reference" && subject ? [subject] : [], anchor_image_id: mode === "anchor_edit" ? anchor?.id : undefined,
      ...(mode === "reference" ? params : {}), idempotency_key: key.current, ...c });
    key.current = crypto.randomUUID();
    onCreated();
  });

  const anchorBody = ref && characterId ? { kind: "motion_anchor" as const, model: anchorModel, character_id: characterId } : null;
  const anchorEst = useEstimate(mode === "anchor_edit" ? anchorBody : null);
  const anchorRun = useConfirmedRun(() => anchorBody, async (c) => {
    const img = await api.makeAnchor({ reference_id: ref!.id, character_id: characterId, model: anchorModel, ...c });
    addImage(img); setAnchor(img); onCreated();
  });

  return (
    <Stage
      canvas={<>
        <div className="motion-pair">
          <div className="preview">
            {ref ? <video key={ref.id} ref={previewRef} src={api.referenceUrl(ref.id)} controls muted playsInline loop />
              : <EmptyState icon={<Footprints size={36} />} title="Pilih video referensi" hint="Gerakan video ini yang akan ditiru." />}
            {ref && <span className="chip meta">{ref.duration.toFixed(1)} dtk · {ref.width}×{ref.height}{ref.has_audio ? " · suara" : ""}{ref.trimmed ? " · dipotong" : ""}</span>}
          </div>
          {mode === "anchor_edit" && (
            <div className="preview">
              {anchor ? <img src={api.imageUrl(anchor.id)} alt="Anchor frame" /> :
                <EmptyState icon={<Sparkles size={30} />} title="Anchor frame" hint="Frame pertama video dengan karakter terpilih." />}
            </div>
          )}
        </div>
        {ref && <TrimPanel refr={ref} max={maxReference} canTrim={publicMedia || !ref.source_clip_id} videoRef={previewRef}
          matchSeconds={mode === "reference" && params.duration ? params.duration : null} onTrimmed={(r) => { setRef(r); setAnchor(null); }} />}
        <Section title="Video referensi dari library">
          {done.length === 0 ? <p className="muted">Belum ada video selesai. Buat dulu di Gambar → Video.</p> : (
            <div className="strip" role="group" aria-label="Klip library">
              {done.map((c) => {
                const stale = Date.now() - new Date(c.created_at).getTime() > STALE_MS;
                return (
                  <button key={c.id} type="button" className={`ref-pick ${ref?.source_clip_id === c.id ? "on" : ""}`} disabled={refBusy}
                    title={stale ? "Klip lebih dari 20 jam: URL-nya mungkin sudah kedaluwarsa" : c.prompt}
                    aria-label={`Pakai klip sebagai referensi: ${c.prompt.slice(0, 60)}`}
                    onClick={() => void loadRef(() => api.referenceFromClip(c.id))}>
                    <video src={`${api.clipUrl(c.id)}#t=0.1`} muted preload="metadata" playsInline />
                    {stale && <span className="pill warn">mungkin kedaluwarsa</span>}
                  </button>
                );
              })}
            </div>
          )}
          {own.length > 0 && <>
            <p className="muted">Referensi tersimpan (unggahan, hasil potong, previs adegan):</p>
            <div className="strip" role="group" aria-label="Referensi tersimpan">
              {own.slice(0, 20).map((r) => (
                <button key={r.id} type="button" className={`ref-pick ${ref?.id === r.id ? "on" : ""}`} disabled={refBusy}
                  title={`${r.duration.toFixed(1)} dtk · ${r.width}×${r.height}`} aria-label={`Pakai referensi tersimpan ${r.duration.toFixed(1)} detik`}
                  onClick={() => void loadRef(async () => r)}>
                  <video src={`${api.referenceUrl(r.id)}#t=0.1`} muted preload="metadata" playsInline />
                  <span className="pill">{r.duration.toFixed(1)}s</span>
                </button>
              ))}
            </div>
          </>}
          <div className="actions">
            <input ref={fileInput} type="file" accept="video/*" hidden
              onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void loadRef(() => api.uploadReference(f)); }} />
            <button className="btn" disabled={!publicMedia || refBusy} onClick={() => fileInput.current?.click()}>
              {refBusy ? <Loader2 size={14} className="spin" /> : <Upload size={14} />} Unggah video
            </button>
            {!publicMedia && <span className="muted">Unggah butuh URL publik karena model mengambil video lewat internet. Isi PUBLIC_TUNNEL=cloudflared di .env (tunnel sementara, butuh cloudflared), atau S3/R2 (S3_BUCKET, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_ENDPOINT_URL), lalu restart backend.</span>}
          </div>
          {refError && <p className="error">{refError}</p>}
        </Section>
      </>}
      inspector={<>
        <Section title="Cara">
          <div className="mode-cards" role="radiogroup" aria-label="Mode tiru gerakan">
            {MODES.map((m) => (
              <button key={m.id} type="button" role="radio" aria-checked={m.id === mode} className={`mode-card ${m.id === mode ? "on" : ""}`} onClick={() => pickMode(m.id)}>
                <strong>{m.title}</strong><span className="muted">{m.hint}</span>
              </button>
            ))}
          </div>
        </Section>
        <Section title={mode === "flux_edit" ? "Karakter (opsional)" : mode === "anchor_edit" ? "Karakter" : "Karakter / gambar subjek"}>
          <select value={characterId} onChange={(e) => { setCharacterId(e.target.value); setAnchor(null); }} aria-label="Karakter">
            <option value="">{mode === "anchor_edit" ? "(pilih karakter)" : "(tanpa karakter)"}</option>
            {characters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          {mode === "flux_edit" && <p className="muted">Model ini hanya membaca teks: deskripsi baku karakter ditambahkan ke prompt.</p>}
          {mode === "flux_edit" && <>
            <label className="field">Subjek baru, dalam kata-kata (dikirim ke FLUX)
              <textarea value={subjectText} onChange={(e) => setSubjectText(e.target.value)} rows={3} maxLength={1000}
                placeholder="wanita muda, rambut bob hitam pendek, jaket kulit merah, kaus putih, jeans" aria-label="Subjek baru" /></label>
            {/\b(foto|photo|image|picture|gambar ini|di gambar)\b/i.test(subjectText) &&
              <p className="warn">Teks ini menyebut foto/gambar. FLUX tidak bisa melihat gambar dan menolak prompt yang merujuk ke media (error 422). Tulis dengan kata-kata: rambut, pakaian, warna.</p>}
          </>}
          {mode === "reference" && <AssetStrip images={images} value={subject} onChange={setSubject} onUploaded={addImage} paste={false} />}
        </Section>
        {mode === "anchor_edit" && (
          <Section title="Langkah 1: anchor frame">
            <ModelPicker kind="image" label="Model gambar" value={anchorModel} onChange={setAnchorModel} />
            <EstimateLine est={anchorEst.est} error={anchorEst.error} />
            {anchorRun.error && <p className="error">{anchorRun.error}</p>}
            <button className="btn block" disabled={!anchorBody || !!anchorEst.est?.blocked} onClick={() => void anchorRun.start()}>
              {anchor ? "Buat ulang anchor frame" : "Buat anchor frame"}
            </button>
            {anchorRun.dialog}
          </Section>
        )}
        {mode === "reference" && (
          <Section title="Model & parameter">
            {seedance.error ? <p className="error">{seedance.error}</p> :
              <ModelParams models={(seedance.data ?? []).filter((m) => SEEDANCE.includes(m.id))} model={seedModel} setModel={setSeedModel} params={params} setParams={setParams} />}
          </Section>
        )}
        <Section title={mode === "anchor_edit" ? "Langkah 2: prompt video" : "Prompt"}>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={4} maxLength={4000} aria-label="Prompt tiru gerakan" data-prompt />
          <p className="muted">Bahasa Inggris, sesuai yang lolos uji. Boleh diubah.</p>
        </Section>
        <Section title="Biaya">
          <EstimateLine est={live.est} error={live.error} />
        </Section>
        {(missing || runner.error) && <p className={runner.error ? "error" : "muted"}>{runner.error ?? missing}</p>}
        <button className="btn primary block" data-generate disabled={!!missing || !prompt.trim() || !live.est || !!live.est.blocked} onClick={() => void runner.start()}>
          <Footprints size={16} /> Buat video
        </button>
        {runner.dialog}
      </>}
    />
  );
}
