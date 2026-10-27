import { useEffect, useState } from "react";
import { ImageIcon, Wand2, X } from "lucide-react";
import { api, EstimateRequest, Img } from "../api";
import { AssetStrip, MultiAssetStrip, useAsync } from "../components";
import { ModelPicker } from "../catalog";
import { EstimateLine, useConfirmedRun, useEstimate } from "../estimate";
import { PromptHelper } from "../prompthelper";
import { EXPRESSION_PRESETS, POSE_PRESETS, Preset, pushHistory } from "../prompts";
import { useTrack } from "../queue";
import { SaveToCharacter } from "../outfits";
import { EmptyState, Section, Stage } from "../ui";

/** Pembanding sebelum/sesudah: geser untuk menyingkap gambar hasil. */
function Compare({ before, after, caption }: { before: string; after: string; caption: string }) {
  const [pos, setPos] = useState(50);
  return (
    <figure style={{ margin: 0 }}>
      <div className="compare">
        <img src={before} alt="sebelum" />
        <div className="after" style={{ clipPath: `inset(0 0 0 ${pos}%)` }}><img src={after} alt="sesudah" /></div>
        <div className="handle" style={{ left: `${pos}%` }} />
        <span className="lbl" style={{ left: 10 }}>Sebelum</span><span className="lbl" style={{ right: 10 }}>Sesudah</span>
        <input type="range" min={0} max={100} value={pos} onChange={(e) => setPos(Number(e.target.value))} aria-label="Geser pembanding" />
      </div>
      <figcaption className="muted" style={{ marginTop: 6 }}>{caption}</figcaption>
    </figure>
  );
}

function PresetChips({ presets, value, onPick }: { presets: Preset[]; value: string; onPick: (text: string) => void }) {
  return (
    <div className="chips">
      {presets.map((p) => (
        <button key={p.label} className={`chip preset ${value === p.text ? "on" : ""}`} title={p.text} aria-pressed={value === p.text}
          onClick={() => onPick(value === p.text ? "" : p.text)}>{p.label}</button>
      ))}
    </div>
  );
}

export default function EditPage({ images, selected, setSelected, addImage, refresh, toVideo }: {
  images: Img[]; selected: string | null; setSelected: (id: string) => void;
  addImage: (i: Img) => void; refresh: () => void; toVideo: (id: string) => void;
}) {
  const track = useTrack();
  const models = useAsync(api.imageModels, []);
  const chars = useAsync(api.characters, []);
  const [characterId, setCharacterId] = useState("");
  const [model, setModel] = useState("openai/gpt-image-2");
  const [prompt, setPrompt] = useState("");
  const [refs, setRefs] = useState<string[]>([]);
  const [poseId, setPoseId] = useState<string | null>(null);
  const [poseMode, setPoseMode] = useState<"sketch" | "original">("sketch");
  const [poseText, setPoseText] = useState("");
  const [exprId, setExprId] = useState<string | null>(null);
  const [exprText, setExprText] = useState("");
  const [opts, setOpts] = useState<{ resolution?: string; aspect_ratio?: string; quality?: string }>({});
  const [results, setResults] = useState<Img[]>([]);
  const [error, setError] = useState<string | null>(null);
  const source = images.find((i) => i.id === selected);
  const info = (models.data ?? []).find((m) => m.id === model);

  // batas total gambar input dari model (termasuk sumber); fallback 5 = perilaku lama (1 sumber + 4 referensi)
  const limit = info?.supported_parameters?.input_references?.max ?? 5;
  const refMax = Math.max(0, Math.min(8, limit - 1 - (poseId ? 1 : 0) - (exprId ? 1 : 0)));
  useEffect(() => { setRefs((r) => (r.length > refMax ? r.slice(0, refMax) : r)); }, [refMax]);
  useEffect(() => {   // satu gambar tidak boleh punya dua peran: sumber baru menyingkirkan peran lain yang sama
    if (poseId === selected) setPoseId(null);
    if (exprId === selected) setExprId(null);
    setRefs((r) => r.filter((x) => x !== selected));
  }, [selected]); // eslint-disable-line react-hooks/exhaustive-deps

  const optionSelect = (label: string, key: "resolution" | "aspect_ratio" | "quality") => {
    const desc = info?.supported_parameters?.[key];
    if (!desc || desc.type !== "enum") return null;
    return (
      <label className="field">{label}
        <select value={opts[key] ?? ""} onChange={(e) => setOpts({ ...opts, [key]: e.target.value || undefined })}>
          <option value="">(default)</option>
          {desc.values?.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
      </label>
    );
  };

  const roles = {
    ...(characterId ? { character_id: characterId } : {}),
    ...(poseId ? { pose_image_id: poseId, pose_mode: poseMode } : {}),
    ...(exprId ? { expression_image_id: exprId } : {}),
    ...(poseText.trim() ? { pose_text: poseText.trim() } : {}),
    ...(exprText.trim() ? { expression_text: exprText.trim() } : {}),
  };
  // berbasis id: server menghitung daftar gambar input yang sama dengan saat generate
  const estBody: EstimateRequest | null = model
    ? { kind: "image_edit", model, ...(selected ? { source_image_id: selected } : {}), reference_image_ids: refs, ...roles, ...opts } : null;
  const live = useEstimate(estBody);
  const runner = useConfirmedRun(() => estBody, async (c) => {
    const out = await track("Edit foto", () => api.editImage(selected!, { prompt, model, reference_image_ids: refs, ...opts, ...roles, ...c }));
    pushHistory(prompt); setResults(out); refresh();
  });

  function submit() {
    if (!selected) return setError("Pilih gambar sumber dulu.");
    setError(null);
    runner.start();
  }
  const toggleRef = (id: string) => setRefs((r) => (r.includes(id) ? r.filter((x) => x !== id) : [...r, id]));
  // tiap section hanya menawarkan gambar yang belum dipakai peran lain
  const free = (...taken: (string | null)[]) => images.filter((i) => i.id !== selected && !taken.includes(i.id));

  return (
    <Stage
      canvas={<>
        {results.length > 0 && source ? (
          <>
            {results.map((r) => (
              <div key={r.id}>
                <Compare before={api.imageUrl(source.id)} after={api.imageUrl(r.id)}
                  caption={`Sesudah (${r.width}×${r.height})${r.cost != null ? ` · biaya $${r.cost}` : ""}${r.estimated_cost != null ? ` (perkiraan $${r.estimated_cost.toFixed(4)})` : ""}`} />
                <div className="actions" style={{ marginTop: 8 }}>
                  <button className="btn" onClick={() => { setSelected(r.id); setResults([]); }}>Edit lagi dari ini</button>
                  <button className="btn" onClick={() => toVideo(r.id)}>Jadikan video</button>
                  <SaveToCharacter imageId={r.id} characters={chars.data ?? []} onSaved={() => api.characters().then(chars.setData)} />
                  <button className="btn ghost" onClick={() => setResults([])}>Tutup hasil</button>
                </div>
              </div>
            ))}
          </>
        ) : (
          <div className="preview">
            {source ? <img src={api.imageUrl(source.id)} alt={source.prompt ?? "gambar sumber"} /> :
              <EmptyState icon={<ImageIcon size={36} />} title="Pilih gambar yang mau diedit" hint="Seret, tempel, atau pilih dari strip di bawah." />}
          </div>
        )}
        <AssetStrip images={images} value={selected} onChange={setSelected} onUploaded={addImage} />
        <p className="muted">Edit berantai bisa menurunkan kualitas dan mengubah wajah; gambar asli selalu tersimpan.</p>
      </>}
      inspector={<>
        <Section title="Prompt edit">
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={4} maxLength={4000} aria-label="Prompt edit"
            placeholder="Ganti latar menjadi hutan berkabut, pertahankan wajah dan pakaian" data-prompt />
          <PromptHelper value={prompt} onChange={setPrompt} groups={["Gaya", "Cahaya"]} />
        </Section>
        <Section title="Model & opsi">
          <ModelPicker kind="image" value={model} onChange={(id) => { setModel(id); setOpts({}); }} />
          <div className="row2">
            {optionSelect("Resolusi", "resolution")}
            {optionSelect("Rasio", "aspect_ratio")}
            {optionSelect("Kualitas", "quality")}
          </div>
          {models.error && <p className="muted">Daftar model tidak termuat: {models.error}</p>}
          <label className="field">Kunci karakter
            <select value={characterId} onChange={(e) => setCharacterId(e.target.value)}>
              <option value="">(tanpa karakter)</option>
              {(chars.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
        </Section>

        <Section title="Pose">
          <p className="muted">Mengubah pose saja. Identitas tetap dari gambar sumber{characterId ? " dan karakter terkunci" : ""}.</p>
          <AssetStrip images={free(exprId, ...refs)} value={poseId} onChange={setPoseId} onUploaded={addImage} paste={false} />
          {poseId && (<>
            <div className="seg" role="group" aria-label="Bentuk referensi pose">
              <button className={poseMode === "sketch" ? "on" : ""} onClick={() => setPoseMode("sketch")}>Sketsa garis (disarankan)</button>
              <button className={poseMode === "original" ? "on" : ""} onClick={() => setPoseMode("original")}>Gambar asli</button>
            </div>
            {poseMode === "sketch"
              ? <img className="sketch" src={api.sketchUrl(poseId)} alt="Pratinjau sketsa pose yang dikirim" />
              : <p className="muted">Gambar asli bisa ikut membawa wajah, baju, dan ekspresi orang di gambar itu.</p>}
            <button className="btn ghost sm" onClick={() => setPoseId(null)}><X size={14} /> Hapus gambar pose</button>
          </>)}
          <PresetChips presets={POSE_PRESETS} value={poseText} onPick={setPoseText} />
          <input value={poseText} onChange={(e) => setPoseText(e.target.value)} maxLength={200} aria-label="Teks pose"
            placeholder="atau tulis pose (Inggris lebih patuh): hands on hips" />
        </Section>

        <Section title="Ekspresi">
          <p className="muted">Mengubah ekspresi wajah saja. Preset teks paling aman untuk menjaga wajah karakter.</p>
          <PresetChips presets={EXPRESSION_PRESETS} value={exprText} onPick={setExprText} />
          <input value={exprText} onChange={(e) => setExprText(e.target.value)} maxLength={200} aria-label="Teks ekspresi"
            placeholder="atau tulis ekspresi: big open smile" />
          <details>
            <summary className="muted">Pakai gambar sebagai referensi ekspresi (opsional)</summary>
            <p className="muted">Gambar ini bisa membawa wajah orang di dalamnya ke hasil; pakai crop wajah atau preset teks bila hasilnya tidak mirip karakter.</p>
            <AssetStrip images={free(poseId, ...refs)} value={exprId} onChange={setExprId} onUploaded={addImage} paste={false} />
            {exprId && <button className="btn ghost sm" onClick={() => setExprId(null)}><X size={14} /> Hapus gambar ekspresi</button>}
          </details>
        </Section>

        <Section title={`Referensi lain (${refs.length}/${refMax})`}>
          <p className="muted">Gaya, properti, atau latar. Tidak dipakai untuk pose atau ekspresi.</p>
          <MultiAssetStrip images={free(poseId, exprId)} values={refs} onToggle={toggleRef} max={refMax} />
        </Section>

        <Section title="Biaya">
          <EstimateLine est={live.est} error={live.error} />
          {live.est?.inputs != null && <p className="muted">{live.est.inputs} gambar input dikirim (batas model {limit}).</p>}
        </Section>
        {(error || runner.error) && <p className="error">{error ?? runner.error}</p>}
        <button className="btn primary block" data-generate disabled={!prompt.trim() || !!live.est?.blocked} onClick={submit}>
          <Wand2 size={16} /> Edit
        </button>
        {runner.dialog}
      </>}
    />
  );
}
