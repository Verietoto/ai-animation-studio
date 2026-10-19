import { useState } from "react";
import { api, Character, Img } from "../api";
import { ImagePicker, useAsync } from "../components";
import { EstimateLine, useConfirmedRun, useEstimate } from "../estimate";

export default function Characters({ images, selected, setSelected, addImage, refreshImages }: {
  images: Img[]; selected: string | null; setSelected: (id: string) => void;
  addImage: (i: Img) => void; refreshImages: () => void;
}) {
  const chars = useAsync(api.characters, []);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const list = chars.data ?? [];
  const reload = () => api.characters().then(chars.setData);

  async function create() {
    if (!selected) return setError("Pilih gambar karakter dulu.");
    setError(null);
    try {
      await api.createCharacter({ name, description, source_image_id: selected });
      setName(""); setDescription(""); reload();
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <section>
      <h2>Karakter</h2>
      <p className="muted">Karakter menyimpan deskripsi baku dan gambar referensi (character sheet) agar wajah dan pakaian tetap konsisten di Edit Foto dan fitur berikutnya.</p>
      <h3>Buat karakter dari gambar</h3>
      <ImagePicker images={images} value={selected} onChange={setSelected} onUploaded={addImage} />
      <div className="row">
        <label>Nama<input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} /></label>
      </div>
      <label className="block">Deskripsi baku (wajah, rambut, pakaian, warna; dipakai di setiap prompt)
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} maxLength={2000}
          placeholder="Wanita muda, rambut bob hitam pendek, jaket merah, kaus putih, anting perak" />
      </label>
      {error && <p className="error">{error}</p>}
      <button className="primary" disabled={!name.trim() || !description.trim()} onClick={create}>Simpan karakter</button>
      <div className="clips" style={{ marginTop: 20 }}>
        {list.map((c) => <CharacterCard key={c.id} c={c} onChange={() => { reload(); refreshImages(); }} />)}
        {list.length === 0 && <p className="muted">Belum ada karakter.</p>}
      </div>
    </section>
  );
}

function CharacterCard({ c, onChange }: { c: Character; onChange: () => void }) {
  const models = useAsync(api.imageModels, []);
  const [model, setModel] = useState("openai/gpt-image-2");
  const estBody = { kind: "character_sheet" as const, model };
  const live = useEstimate(estBody);
  const runner = useConfirmedRun(() => estBody, async (conf) => { await api.makeSheet(c.id, { model, ...conf }); onChange(); });
  const hasSheet = c.images.some((i) => i.label !== "source" && i.label !== "custom");
  return (
    <article className="clip">
      <strong>{c.name}</strong>
      <p className="prompt">{c.description}</p>
      <div className="thumbs">
        {c.images.map((i) => (
          <figure key={i.image_id} style={{ margin: 0 }}>
            <img src={api.imageUrl(i.image_id)} alt={i.label} style={{ width: 72, height: 72, objectFit: "cover", borderRadius: 6 }} />
            <figcaption className="muted">{i.label}</figcaption>
          </figure>
        ))}
      </div>
      <label>Model sheet
        <input list="sheet-models" value={model} onChange={(e) => setModel(e.target.value)} />
        <datalist id="sheet-models">{(models.data ?? []).map((m) => <option key={m.id} value={m.id} />)}</datalist>
      </label>
      <EstimateLine est={live.est} error={live.error} />
      {runner.error && <p className="error">{runner.error}</p>}
      <button disabled={!!live.est?.blocked} onClick={runner.start}>{hasSheet ? "Buat ulang character sheet" : "Buat character sheet (4 gambar)"}</button>
      {runner.dialog}
    </article>
  );
}
