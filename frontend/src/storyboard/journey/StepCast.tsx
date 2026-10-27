// Langkah 1 alur episode: pilih karakter dan latar yang muncul di episode ini (plan 15).
import { useState } from "react";
import { ImageOff, MapPin, Plus, UserRound } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, Character, Img, JourneyState, Location } from "../../api";
import { CharacterCreator } from "../../characters/CharacterCreator";
import { SaveText } from "../fields";
import { LocationImagePanel } from "../Generate";

export function StepCast({ filmId, journey, characters, locations, images, locked, addImage, reload, reloadLocations, reloadCharacters, onGenerated, onManageLocations }: {
  filmId: string; journey: JourneyState; characters: Character[]; locations: Location[]; images: Img[]; locked: boolean;
  addImage: (i: Img) => void; reload: () => Promise<unknown>; reloadLocations: () => void; reloadCharacters: () => void;
  onGenerated: () => void; onManageLocations: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [newLoc, setNewLoc] = useState("");
  const inChars = new Set(journey.characters.map((c) => c.id));
  const inLocs = new Set(journey.locations.map((l) => l.id));
  const sheetless = new Set(journey.characters.filter((c) => !c.has_sheet).map((c) => c.id));

  async function save(characterIds: string[], locationIds: string[], release = false): Promise<void> {
    setBusy(true);
    try {
      await api.setEpisodeCast(filmId, { character_ids: characterIds, location_ids: locationIds, release });
      await reload();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && !release && window.confirm(`${e.message}\n\nLepaskan dari adegan itu juga?`)) {
        setBusy(false); return save(characterIds, locationIds, true);
      }
      if (!(e instanceof ApiError && e.status === 409)) toast.error((e as Error).message);
    } finally { setBusy(false); }
  }
  const toggleChar = (id: string) => save(inChars.has(id) ? [...inChars].filter((x) => x !== id) : [...inChars, id], [...inLocs]);
  const toggleLoc = (id: string) => save([...inChars], inLocs.has(id) ? [...inLocs].filter((x) => x !== id) : [...inLocs, id]);

  async function createLoc() {
    const name = newLoc.trim();
    if (!name) return;
    try {
      const l = await api.createLocation({ name });
      setNewLoc(""); reloadLocations();
      await save([...inChars], [...inLocs, l.id]);
    } catch (e) { toast.error((e as Error).message); }
  }

  return (
    <div className="jr-cols">
      <section className="jr-card" aria-label="Karakter episode">
        <h3><UserRound size={14} /> Karakter di episode ini <span className="chip">{inChars.size}</span></h3>
        <p className="muted">Centang yang muncul di episode ini. Satu adegan tetap maksimal 3 pemeran; di sini boleh lebih banyak.</p>
        <ul className="jr-pick">
          {characters.map((c) => (
            <li key={c.id}>
              <label className={inChars.has(c.id) ? "on" : ""}>
                <input type="checkbox" checked={inChars.has(c.id)} disabled={locked || busy} onChange={() => void toggleChar(c.id)} />
                <img src={api.imageUrl(c.source_image_id)} alt="" loading="lazy" />
                <span className="clamp1"><strong>{c.name}</strong></span>
                {sheetless.has(c.id) && <span className="chip meta" title="Belum ada lembar tampilan; hasil keyframe kurang konsisten">tanpa lembar tampilan</span>}
              </label>
            </li>
          ))}
        </ul>
        {characters.length === 0 && <p className="muted">Belum ada karakter di workspace ini.</p>}
        <details className="pick jr-new">
          <summary><Plus size={13} /> Karakter baru</summary>
          <CharacterCreator images={images} characters={characters} addImage={addImage} refreshImages={onGenerated}
            onCreated={async (c) => { reloadCharacters(); await save([...inChars, c.id], [...inLocs]); }} />
        </details>
      </section>
      <section className="jr-card" aria-label="Latar episode">
        <h3><MapPin size={14} /> Latar di episode ini <span className="chip">{inLocs.size}</span></h3>
        <p className="muted">Latar yang bergambar dipakai untuk keyframe. Buka "Deskripsi &amp; gambar" untuk membuat gambarnya dari deskripsi.</p>
        <ul className="jr-pick">
          {locations.map((l) => (
            <li key={l.id}>
              <label className={inLocs.has(l.id) ? "on" : ""}>
                <input type="checkbox" checked={inLocs.has(l.id)} disabled={locked || busy} onChange={() => void toggleLoc(l.id)} />
                {l.image_id ? <img src={api.imageUrl(l.image_id)} alt="" loading="lazy" /> : <span className="jr-noimg"><ImageOff size={16} /></span>}
                <span className="clamp1"><strong>{l.name}</strong></span>
                {!l.image_id && <span className="chip meta" title="Tanpa gambar, keyframe tidak bisa dibuat untuk latar ini">tanpa gambar</span>}
              </label>
              <details className="pick jr-loc">
                <summary>Deskripsi &amp; gambar</summary>
                <SaveText label="Deskripsi latar" multiline rows={2} value={l.description} maxLength={300} placeholder="Suasana, benda, cuaca…"
                  onSave={async (v) => { await api.updateLocation(l.id, { description: v }); reloadLocations(); }} />
                <LocationImagePanel loc={l} onDone={() => { reloadLocations(); onGenerated(); void reload(); }} />
              </details>
            </li>
          ))}
        </ul>
        <form className="jr-inline" onSubmit={(e) => { e.preventDefault(); void createLoc(); }}>
          <input value={newLoc} onChange={(e) => setNewLoc(e.target.value)} placeholder="Latar baru, mis. Warung kopi" maxLength={60} aria-label="Nama latar baru" />
          <button className="btn sm" disabled={!newLoc.trim() || locked || busy}><Plus size={13} /> Tambah</button>
        </form>
        <button className="btn ghost sm" onClick={onManageLocations}>Kelola gambar & deskripsi latar…</button>
      </section>
    </div>
  );
}
