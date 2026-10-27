import { useEffect, useRef, useState } from "react";
import { ImageIcon, Sparkles, X } from "lucide-react";
import { api, Img } from "../api";
import { AssetStrip, ModelParams, NegativePrompt, supportsNegative, useAsync, VideoParams } from "../components";
import { EstimateLine, useConfirmedRun, useEstimate } from "../estimate";
import { PromptHelper } from "../prompthelper";
import { pushHistory } from "../prompts";
import { EmptyState, Section, Stage } from "../ui";

export default function Generate({ images, selected, setSelected, addImage, onCreated }: {
  images: Img[]; selected: string | null; setSelected: (id: string) => void;
  addImage: (i: Img) => void; onCreated: () => void;
}) {
  const models = useAsync(api.videoModels, []);
  const [model, setModel] = useState("");
  const [params, setParams] = useState<VideoParams>({ generate_audio: false });
  const [prompt, setPrompt] = useState("");
  const [negative, setNegative] = useState("");   // plan 13
  const [error, setError] = useState<string | null>(null);
  const key = useRef(crypto.randomUUID()); // satu kunci per percobaan; klik ganda tidak membuat job ganda
  const source = images.find((i) => i.id === selected);
  const [last, setLast] = useState<string | null>(null);   // frame akhir opsional (plan 09)
  const canLast = !!models.data?.find((m) => m.id === model)?.supported_frame_images?.includes("last_frame");
  useEffect(() => { if (!canLast) setLast(null); }, [canLast]);
  const lastImg = canLast ? images.find((i) => i.id === last) : undefined;
  const ratioOff = source && lastImg && Math.abs(source.width / source.height - lastImg.width / lastImg.height) > 0.1 * (source.width / source.height);

  const estBody = model ? { kind: "video" as const, model, ...params } : null;
  const live = useEstimate(estBody);
  const runner = useConfirmedRun(() => estBody, async (c) => {
    await api.createClip({ image_id: selected, prompt, model, ...params, last_image_id: lastImg?.id,
      negative_prompt: supportsNegative(models.data ?? [], model) ? negative.trim() || undefined : undefined, idempotency_key: key.current, ...c });
    key.current = crypto.randomUUID();
    pushHistory(prompt);
    onCreated();
  });

  function submit() {
    if (!selected) return setError("Pilih atau unggah gambar dulu.");
    if (!model) return setError("Pilih model.");
    setError(null);
    runner.start();
  }

  return (
    <Stage
      canvas={<>
        <div className="preview">
          {source ? <img src={api.imageUrl(source.id)} alt={source.prompt ?? "gambar sumber"} /> :
            <EmptyState icon={<ImageIcon size={36} />} title="Pilih atau unggah gambar awal"
              hint="Seret file ke sini, tempel dari clipboard, atau klik + di bawah." />}
          {source && <span className="chip meta">{source.width}×{source.height} · {source.kind}</span>}
          {lastImg && <figure className="last-frame"><img src={api.imageUrl(lastImg.id)} alt="Frame akhir" /><figcaption>frame akhir</figcaption></figure>}
        </div>
        <AssetStrip images={images} value={selected} onChange={setSelected} onUploaded={addImage} />
      </>}
      inspector={<>
        <Section title="Prompt gerakan">
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={4} maxLength={4000}
            placeholder="Kamera bergerak pelan mendekat, rambut tertiup angin…" aria-label="Prompt gerakan" data-prompt />
          <PromptHelper value={prompt} onChange={setPrompt} groups={["Kamera", "Gaya", "Cahaya"]} />
        </Section>
        <Section title="Model & parameter">
          {models.error ? <p className="error">{models.error}</p> :
            <ModelParams models={models.data ?? []} model={model} setModel={setModel} params={params} setParams={setParams} />}
          <NegativePrompt models={models.data ?? []} model={model} value={negative} onChange={setNegative} />
        </Section>
        {canLast && (
          <Section title="Frame akhir (opsional)">
            <p className="muted">Video berakhir di gambar ini, jadi model membuat transisi dari gambar awal ke gambar ini. Eksperimental.</p>
            <AssetStrip images={images} value={last} onChange={setLast} onUploaded={addImage} paste={false} />
            {lastImg && <button className="btn ghost sm" onClick={() => setLast(null)}><X size={13} /> Tanpa frame akhir</button>}
            {ratioOff && <p className="warn">Rasio frame awal dan akhir berbeda jauh; hasilnya bisa terpotong atau melar.</p>}
          </Section>
        )}
        <Section title="Biaya">
          <EstimateLine est={live.est} error={live.error} />
        </Section>
        {(error || runner.error) && <p className="error">{error ?? runner.error}</p>}
        <button className="btn primary block" data-generate disabled={!prompt.trim() || !!live.est?.blocked} onClick={submit}>
          <Sparkles size={16} /> Buat video
        </button>
        {runner.dialog}
      </>}
    />
  );
}
