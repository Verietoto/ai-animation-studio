// Form karakter baru (plan 16): referensi opsional. Dengan referensi (unggah / pilih dari library) gambar itu dipakai apa adanya;
// tanpa referensi, gambar potret dibuat dari deskripsi (teks ke gambar, satu gambar per klik, dialog biaya tiap klik).
import { useState } from "react";
import { Sparkles } from "lucide-react";
import { api, Character, EstimateRequest, Img } from "../api";
import { AssetStrip } from "../components";
import { ModelPicker } from "../catalog";
import { EstimateLine, useConfirmedRun, useEstimate } from "../estimate";
import { Section } from "../ui";
import { DEFAULT_IMAGE_MODEL } from "../storyboard/Generate";

export function CharacterCreator({ images, characters, addImage, refreshImages, onCreated, selected, setSelected }: {
  images: Img[]; characters: Character[]; addImage: (i: Img) => void; refreshImages: () => void;
  onCreated: (c: Character) => void | Promise<unknown>;
  /** Pilihan gambar boleh dikendalikan induk (halaman Karakter berbagi pilihan dengan halaman lain); bila tidak, dipakai state sendiri. */
  selected?: string | null; setSelected?: (id: string) => void;
}) {
  const [own, setOwn] = useState<string | null>(null);
  const sel = selected !== undefined ? selected : own;
  const choose = (id: string) => (setSelected ?? setOwn)(id);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [model, setModel] = useState(DEFAULT_IMAGE_MODEL);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const body: EstimateRequest | null = description.trim() && model ? { kind: "character_portrait", model, description: description.trim() } : null;
  const live = useEstimate(body);
  const runner = useConfirmedRun(() => body, async (c) => {
    const img = await api.characterPortrait({ description: description.trim(), model, ...c });
    addImage(img); choose(img.id); refreshImages();
  });
  const used = new Set(characters.map((c) => c.source_image_id));
  const unusedPortraits = images.filter((i) => i.kind === "portrait" && !used.has(i.id)).length;

  async function save() {
    if (!sel) return setError("Pilih atau buat gambar karakter dulu.");
    setError(null); setSaving(true);
    try {
      const c = await api.createCharacter({ name: name.trim(), description: description.trim(), source_image_id: sel });
      setName(""); setDescription("");
      await onCreated(c);
    } catch (e) { setError((e as Error).message); } finally { setSaving(false); }
  }

  return (
    <>
      <Section title="Detail">
        <label className="field">Nama<input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} aria-label="Nama karakter" /></label>
        <label className="field">Deskripsi baku (wajah, rambut, pakaian, warna, gaya visual; dipakai di setiap prompt)
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4} maxLength={2000}
            placeholder="Gadis desa 17 tahun, rambut hitam dikepang dua, kebaya merah, gaya anime berwarna cerah" aria-label="Deskripsi karakter" />
        </label>
        <p className="muted">Tulis gayanya (anime, kartun 2D, 3D, atau realistis). Gaya foto-realistik ditolak model video Seedance.</p>
      </Section>
      <Section title="Gambar karakter (referensi opsional)">
        <p className="muted">Punya gambar? Unggah atau pilih di bawah; gambar itu dipakai apa adanya. Tidak punya? Buat dari deskripsi.</p>
        <AssetStrip images={images} value={sel ?? null} onChange={choose} onUploaded={addImage} />
        <div className="gen">
          <ModelPicker kind="image" label="Model gambar" value={model} onChange={setModel} />
          <EstimateLine est={live.est} error={body ? live.error : null} />
          {runner.error && <p className="error">{runner.error}</p>}
          <button className="btn" disabled={!body || !!live.error || !live.est || !!live.est.blocked} onClick={() => void runner.start()}>
            <Sparkles size={14} /> Buat gambar dari deskripsi
          </button>
          <p className="muted">Satu gambar per klik; klik lagi untuk variasi lain. Tampak depan, seluruh badan, latar polos.{unusedPortraits > 0 ? ` ${unusedPortraits} potret belum dipakai (hapus yang tidak perlu di Library).` : ""}</p>
        </div>
        {runner.dialog}
      </Section>
      {error && <p className="error">{error}</p>}
      <button className="btn primary block" disabled={saving || !name.trim() || !description.trim()} onClick={() => void save()}>Simpan karakter</button>
    </>
  );
}
