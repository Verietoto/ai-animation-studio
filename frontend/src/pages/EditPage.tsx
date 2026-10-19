import { useState } from "react";
import { api, Img } from "../api";
import { ImagePicker, useAsync } from "../components";

export default function EditPage({ images, selected, setSelected, addImage, refresh, toVideo }: {
  images: Img[]; selected: string | null; setSelected: (id: string) => void;
  addImage: (i: Img) => void; refresh: () => void; toVideo: (id: string) => void;
}) {
  const models = useAsync(api.imageModels, []);
  const [model, setModel] = useState("openai/gpt-image-2");
  const [prompt, setPrompt] = useState("");
  const [refs, setRefs] = useState<string[]>([]);
  const [opts, setOpts] = useState<{ resolution?: string; aspect_ratio?: string; quality?: string }>({});
  const [results, setResults] = useState<Img[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const source = images.find((i) => i.id === selected);
  const info = (models.data ?? []).find((m) => m.id === model);
  const optionSelect = (label: string, key: "resolution" | "aspect_ratio" | "quality") => {
    const desc = info?.supported_parameters?.[key];
    if (!desc || desc.type !== "enum") return null;
    return (
      <label>{label}
        <select value={opts[key] ?? ""} onChange={(e) => setOpts({ ...opts, [key]: e.target.value || undefined })}>
          <option value="">(default)</option>
          {desc.values?.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
      </label>
    );
  };

  async function submit() {
    if (!selected) return setError("Pilih gambar sumber dulu.");
    setBusy(true); setError(null);
    try {
      const out = await api.editImage(selected, { prompt, model, reference_image_ids: refs, ...opts });
      setResults(out); refresh();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <section>
      <h2>Edit Foto dengan Prompt</h2>
      <ImagePicker images={images} value={selected} onChange={setSelected} onUploaded={addImage} />
      <label className="block">Prompt edit
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} maxLength={4000}
          placeholder="Ganti latar menjadi hutan berkabut, pertahankan wajah dan pakaian" />
      </label>
      <div className="row">
        <label>Model
          <input list="img-models" value={model} onChange={(e) => { setModel(e.target.value); setOpts({}); }} />
          <datalist id="img-models">{(models.data ?? []).map((m) => <option key={m.id} value={m.id} />)}</datalist>
        </label>
        {optionSelect("Resolusi", "resolution")}
        {optionSelect("Rasio", "aspect_ratio")}
        {optionSelect("Kualitas", "quality")}
        <label>Referensi tambahan (opsional, maks 4)
          <select multiple value={refs} onChange={(e) =>
            setRefs(Array.from(e.target.selectedOptions).map((o) => o.value).slice(0, 4))}>
            {images.filter((i) => i.id !== selected).map((i) => <option key={i.id} value={i.id}>{i.prompt ?? i.kind} ({i.id.slice(0, 6)})</option>)}
          </select>
        </label>
      </div>
      {models.error && <p className="muted">Daftar model tidak termuat: {models.error}</p>}
      {error && <p className="error">{error}</p>}
      <button className="primary" disabled={busy || !prompt.trim()} onClick={submit}>{busy ? "Mengedit…" : "Edit"}</button>
      <p className="muted">Edit berantai bisa menurunkan kualitas dan mengubah wajah; gambar asli selalu tersimpan.</p>
      {results.length > 0 && (
        <div className="compare">
          {source && <figure><img src={api.imageUrl(source.id)} alt="sebelum" /><figcaption>Sebelum</figcaption></figure>}
          {results.map((r) => (
            <figure key={r.id}>
              <img src={api.imageUrl(r.id)} alt="sesudah" />
              <figcaption>Sesudah ({r.width}×{r.height}){r.cost != null && ` · $${r.cost}`}</figcaption>
              <button onClick={() => { setSelected(r.id); }}>Edit lagi dari ini</button>
              <button onClick={() => toVideo(r.id)}>Jadikan video</button>
            </figure>
          ))}
        </div>
      )}
    </section>
  );
}
