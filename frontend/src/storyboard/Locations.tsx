import { useState } from "react";
import { MapPin, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, Img, Location } from "../api";
import { AssetStrip } from "../components";
import { EmptyState } from "../ui";
import { SaveText } from "./fields";
import { LocationImagePanel } from "./Generate";

function LocationCard({ loc, images, reload, onGenerated }: { loc: Location; images: Img[]; reload: () => void; onGenerated: () => void }) {
  const [confirmDel, setConfirmDel] = useState(false);
  const save = (body: { name?: string; description?: string; image_id?: string | null }) =>
    api.updateLocation(loc.id, body).then(reload).catch((e: Error) => { toast.error(e.message); throw e; });
  return (
    <article className="card">
      <div className="loc-img">
        {loc.image_id ? <img src={api.imageUrl(loc.image_id)} alt={loc.name} /> : <div className="placeholder" style={{ height: "100%", margin: 0 }}><MapPin size={22} /></div>}
      </div>
      <SaveText label="Nama latar" value={loc.name} maxLength={60} className="sb-title" onSave={(v) => save({ name: v })} />
      <SaveText label="Deskripsi latar" multiline rows={3} value={loc.description} maxLength={300}
        placeholder="Dipakai di prompt: suasana, benda, cuaca…" onSave={(v) => save({ description: v })} />
      <p className="muted">Dipakai di {loc.used} adegan.</p>
      <details className="pick">
        <summary>{loc.image_id ? "Buat ulang gambar dari deskripsi" : "Buat gambar dari deskripsi"}</summary>
        <LocationImagePanel loc={loc} onDone={() => { reload(); onGenerated(); }} />
      </details>
      <details className="pick">
        <summary>{loc.image_id ? "Ganti gambar latar dari library" : "Pasang gambar latar dari library"}</summary>
        <div className="pick-grid">
          {images.slice(0, 60).map((i) => (
            <button key={i.id} className={`thumb ${i.id === loc.image_id ? "sel" : ""}`} aria-label="Pilih gambar latar"
              onClick={() => void save({ image_id: i.id }).catch(() => {})}><img src={api.imageUrl(i.id)} alt="" loading="lazy" /></button>
          ))}
        </div>
        {loc.image_id && <button className="btn ghost sm" onClick={() => void save({ image_id: "" }).catch(() => {})}>Lepas gambar</button>}
      </details>
      {confirmDel ? (
        <div className="actions">
          <button className="btn danger" onClick={() => api.deleteLocation(loc.id).then(reload).catch((e: Error) => toast.error(e.message))}>
            <Trash2 size={14} /> Ya, hapus latar</button>
          <button className="btn ghost" onClick={() => setConfirmDel(false)}>Batal</button>
          <span className="muted">Adegan tetap ada tanpa latar; gambar tetap di library.</span>
        </div>
      ) : <button className="btn ghost danger" onClick={() => setConfirmDel(true)}><Trash2 size={14} /> Hapus latar</button>}
    </article>
  );
}

/** Daftar latar workspace: dipakai ulang di banyak adegan. */
export function LocationsView({ locations, images, addImage, reload, onGenerated }: {
  locations: Location[]; images: Img[]; addImage: (i: Img) => void; reload: () => void; onGenerated: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [imageId, setImageId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setError(null);
    try {
      await api.createLocation({ name, description, image_id: imageId });
      setName(""); setDescription(""); setImageId(null); reload();
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <>
      <p className="muted">Latar adalah tempat kejadian yang dipakai ulang di banyak adegan. Gambar latar nanti menjadi dasar keyframe.</p>
      <section className="card">
        <strong>Latar baru</strong>
        <label className="field">Nama<input value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="Sawah di kaki gunung" /></label>
        <label className="field">Deskripsi (masuk prompt)
          <textarea value={description} rows={2} maxLength={300} onChange={(e) => setDescription(e.target.value)} placeholder="Pematang sempit, kabut tipis, gubuk bambu" /></label>
        <span className="muted">Gambar (opsional): klik +, seret ke sini, atau tempel (⌘V / Ctrl+V) dari clipboard</span>
        <AssetStrip images={images} value={imageId} onChange={setImageId} onUploaded={addImage} />
        {imageId && <button className="btn ghost sm" onClick={() => setImageId(null)}>Tanpa gambar</button>}
        {error && <p className="error">{error}</p>}
        <button className="btn primary" disabled={!name.trim()} onClick={() => void create()}>Simpan latar</button>
      </section>
      {locations.length === 0
        ? <EmptyState icon={<MapPin size={36} />} title="Belum ada latar" hint="Buat di atas, atau langsung dari dropdown Latar di inspector adegan." />
        : <div className="grid">{locations.map((l) => <LocationCard key={l.id} loc={l} images={images} reload={reload} onGenerated={onGenerated} />)}</div>}
    </>
  );
}
