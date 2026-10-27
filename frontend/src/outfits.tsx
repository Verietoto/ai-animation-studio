import { ItemRef } from "./lightbox";
import { useState } from "react";
import { Shirt, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, Character, Img } from "./api";
import { AssetStrip } from "./components";

/** Lemari tampilan/baju satu karakter. Tampilan = gambar karakter yang sudah memakai baju itu (dibuat di Edit Foto), atau deskripsi teks saja. */
export function OutfitSection({ c, images, addImage, onChange, onOpen }: { onOpen: (r: ItemRef) => void; c: Character; images: Img[]; addImage: (i: Img) => void; onChange: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [imageId, setImageId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  async function create() {
    setError(null);
    try {
      await api.createOutfit(c.id, { name, description, image_id: imageId });
      setName(""); setDescription(""); setImageId(null); onChange();
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <details className="pick outfits">
      <summary><Shirt size={13} /> Tampilan / baju ({c.outfits.length})</summary>
      <p className="muted">Pilih tampilan ini per adegan di Storyboard. Paling konsisten bila bergambar: buat di Edit Foto lalu "Simpan ke karakter".</p>
      {c.outfits.map((o) => (
        <div className="outfit-row" key={o.id}>
          {o.image_id ? <button type="button" className="thumb-btn" aria-label={`Buka gambar ${o.name}`} onClick={() => onOpen({ type: "image", id: o.image_id! })}><img src={api.imageUrl(o.image_id)} alt={o.name} /></button> : <span className="outfit-text" title="Hanya teks">teks</span>}
          <div className="job-main"><strong className="clamp1">{o.name}</strong><span className="muted clamp1">{o.description || "gambar saja"}</span></div>
          {confirmId === o.id
            ? <button className="btn danger sm" onClick={() => api.deleteOutfit(o.id).then(() => { setConfirmId(null); onChange(); }).catch((e: Error) => toast.error(e.message))}>Yakin hapus</button>
            : <button className="btn ghost sm" aria-label={`Hapus tampilan ${o.name}`} onClick={() => setConfirmId(o.id)}><Trash2 size={13} /></button>}
        </div>
      ))}
      <label className="field">Nama tampilan<input value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="Kebaya merah" /></label>
      <label className="field">Deskripsi (masuk prompt bila tanpa gambar)
        <input value={description} maxLength={300} onChange={(e) => setDescription(e.target.value)} placeholder="kebaya merah bata, kain batik cokelat" /></label>
      <span className="muted">Gambar karakter dengan baju ini (opsional)</span>
      <AssetStrip images={images} value={imageId} onChange={setImageId} onUploaded={addImage} paste={false} />
      {imageId && <button className="btn ghost sm" onClick={() => setImageId(null)}>Tanpa gambar</button>}
      {error && <p className="error">{error}</p>}
      <button className="btn" disabled={!name.trim() || (!imageId && !description.trim())} onClick={() => void create()}>Simpan tampilan</button>
    </details>
  );
}

/** Dari hasil Edit Foto: simpan gambar ke karakter sebagai tampilan/baju atau sebagai sudut sheet. */
export function SaveToCharacter({ imageId, characters, onSaved }: { imageId: string; characters: Character[]; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [characterId, setCharacterId] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const target = characterId || characters[0]?.id || "";

  async function save(kind: "outfit" | "sheet") {
    setBusy(true);
    try {
      if (kind === "outfit") await api.createOutfit(target, { name, image_id: imageId });
      else await api.addCharacterImage(target, imageId);
      const who = characters.find((c) => c.id === target)?.name ?? "karakter";
      toast.success(kind === "outfit" ? `Disimpan sebagai tampilan "${name}" untuk ${who}` : `Ditambahkan ke sheet ${who}`);
      setOpen(false); setName(""); onSaved();
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  }

  if (!open) return <button className="btn" onClick={() => setOpen(true)} disabled={characters.length === 0} title={characters.length === 0 ? "Buat karakter dulu" : undefined}><Shirt size={14} /> Simpan ke karakter…</button>;
  return (
    <div className="save-char">
      <select aria-label="Karakter" value={target} onChange={(e) => setCharacterId(e.target.value)}>
        {characters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
      <input value={name} maxLength={60} placeholder="Nama tampilan, mis. Kebaya merah" aria-label="Nama tampilan" onChange={(e) => setName(e.target.value)} />
      <div className="actions">
        <button className="btn primary sm" disabled={busy || !name.trim()} onClick={() => void save("outfit")}>Simpan sebagai tampilan</button>
        <button className="btn sm" disabled={busy} onClick={() => void save("sheet")}>Tambah ke sheet</button>
        <button className="btn ghost sm" onClick={() => setOpen(false)}>Batal</button>
      </div>
    </div>
  );
}
