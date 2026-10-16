import { useRef, useState } from "react";
import { api, Img } from "../api";
import { ImagePicker, ModelParams, useAsync, VideoParams } from "../components";

export default function Generate({ images, selected, setSelected, addImage, onCreated }: {
  images: Img[]; selected: string | null; setSelected: (id: string) => void;
  addImage: (i: Img) => void; onCreated: () => void;
}) {
  const models = useAsync(api.videoModels, []);
  const [model, setModel] = useState("");
  const [params, setParams] = useState<VideoParams>({ generate_audio: false });
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = useRef(crypto.randomUUID()); // satu kunci per percobaan; klik ganda tidak membuat job ganda

  async function submit() {
    if (!selected) return setError("Pilih atau unggah gambar dulu.");
    if (!model) return setError("Pilih model.");
    setBusy(true); setError(null);
    try {
      await api.createClip({ image_id: selected, prompt, model, ...params, idempotency_key: key.current });
      key.current = crypto.randomUUID();
      onCreated();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <section>
      <h2>Gambar → Video</h2>
      <ImagePicker images={images} value={selected} onChange={setSelected} onUploaded={addImage} />
      <label className="block">Prompt gerakan
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} maxLength={4000}
          placeholder="Kamera bergerak pelan mendekat, rambut tertiup angin…" />
      </label>
      {models.error ? <p className="error">{models.error}</p> :
        <ModelParams models={models.data ?? []} model={model} setModel={setModel} params={params} setParams={setParams} />}
      {error && <p className="error">{error}</p>}
      <button className="primary" disabled={busy || !prompt.trim()} onClick={submit}>
        {busy ? "Mengirim…" : "Buat video"}
      </button>
      <p className="muted">Biaya ditagih per job oleh provider. Batas harian dijaga di server.</p>
    </section>
  );
}
