import { useState } from "react";
import { Copy, Trash2, UserRound } from "lucide-react";
import { useWorkspaces } from "../workspaces";
import { api, Character, Img } from "../api";
import { useAsync } from "../components";
import { CharacterCreator } from "../characters/CharacterCreator";
import { ModelPicker } from "../catalog";
import { useTrack } from "../queue";
import { EstimateLine, useConfirmedRun, useEstimate } from "../estimate";
import { ItemRef } from "../lightbox";
import { OutfitSection } from "../outfits";
import { EmptyState, Stage } from "../ui";

export default function Characters({ images, selected, setSelected, addImage, refreshImages, onOpen }: {
  onOpen: (r: ItemRef) => void;
  images: Img[]; selected: string | null; setSelected: (id: string) => void;
  addImage: (i: Img) => void; refreshImages: () => void;
}) {
  const chars = useAsync(api.characters, []);
  const list = chars.data ?? [];
  const reload = () => api.characters().then(chars.setData);

  return (
    <Stage
      canvas={<>
        <p className="muted">Karakter menyimpan deskripsi baku dan gambar referensi (character sheet) agar wajah dan pakaian tetap konsisten di Edit Foto dan fitur berikutnya.</p>
        {chars.error && <p className="error">{chars.error}</p>}
        <div className="grid">
          {list.map((c) => <CharacterCard key={c.id} c={c} onOpen={onOpen} images={images} addImage={addImage} onChange={() => { reload(); refreshImages(); }} />)}
        </div>
        {list.length === 0 && <EmptyState icon={<UserRound size={36} />} title="Belum ada karakter"
          hint="Beri nama dan deskripsi di panel kanan, lalu unggah gambar atau buat dari deskripsi." />}
      </>}
      inspector={<CharacterCreator images={images} characters={list} addImage={addImage} refreshImages={refreshImages}
        selected={selected} setSelected={setSelected} onCreated={() => { void reload(); refreshImages(); }} />}
    />
  );
}

function CharacterCard({ c, images, addImage, onChange, onOpen }: { onOpen: (r: ItemRef) => void; c: Character; images: Img[]; addImage: (i: Img) => void; onChange: () => void }) {
  const [model, setModel] = useState("openai/gpt-image-2");
  const { askCopy } = useWorkspaces();
  const [confirmDel, setConfirmDel] = useState(false);
  const [delError, setDelError] = useState<string | null>(null);
  const estBody = { kind: "character_sheet" as const, model };
  const live = useEstimate(estBody);
  const track = useTrack();
  const runner = useConfirmedRun(() => estBody, async (conf) => {
    await track(`Character sheet: ${c.name}`, () => api.makeSheet(c.id, { model, ...conf }));
    onChange();
  });
  const hasSheet = c.images.some((i) => i.label !== "source" && i.label !== "custom");
  return (
    <article className="card">
      <strong>{c.name}</strong>
      <p className="prompt">{c.description}</p>
      <div className="strip">
        {c.images.map((i) => (
          <figure key={i.image_id} style={{ margin: 0, flex: "0 0 auto" }}>
            <button type="button" className="thumb-btn" aria-label={`Buka gambar ${i.label}`} onClick={() => onOpen({ type: "image", id: i.image_id })}>
              <img src={api.imageUrl(i.image_id)} alt={i.label} style={{ width: 72, height: 72, objectFit: "cover", borderRadius: 8, display: "block" }} />
            </button>
            <figcaption className="muted" style={{ fontSize: 11 }}>{i.label}</figcaption>
          </figure>
        ))}
      </div>
      <OutfitSection onOpen={onOpen} c={c} images={images} addImage={addImage} onChange={onChange} />
      <ModelPicker kind="image" label="Model sheet" value={model} onChange={setModel} />
      <EstimateLine est={live.est} error={live.error} />
      {runner.error && <p className="error">{runner.error}</p>}
      <button className="btn" disabled={!!live.est?.blocked} onClick={runner.start}>
        {hasSheet ? "Buat ulang character sheet" : "Buat character sheet (1 gambar, 4 sudut)"}
      </button>
      <button className="btn ghost" onClick={() => askCopy([], [c.id])}><Copy size={14} /> Salin ke workspace…</button>
      {delError && <p className="error">{delError}</p>}
      {confirmDel ? (
        <div className="actions">
          <button className="btn danger" onClick={() => api.deleteCharacter(c.id).then(onChange).catch((e: Error) => setDelError(e.message))}>
            <Trash2 size={14} /> Ya, hapus karakter</button>
          <button className="btn ghost" onClick={() => setConfirmDel(false)}>Batal</button>
          <span className="muted">Gambar tetap ada di library; pemeran di adegan dilepas.</span>
        </div>
      ) : <button className="btn ghost danger" onClick={() => { setConfirmDel(true); setDelError(null); }}><Trash2 size={14} /> Hapus karakter</button>}
      {runner.dialog}
    </article>
  );
}
