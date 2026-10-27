// Editor "prompt adegan" (plan 18 Revisi 8): SATU-SATUNYA sumber latar, pemeran, beat, mood, dan durasi adegan di Storyboard v2.
// Mention `@[Karakter]` / `#[Latar]` terhubung ke aset proyek; nomor @image_N baru ditentukan server saat video dikirim.
import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Bot, ImageOff, Loader2, Save } from "lucide-react";
import { toast } from "sonner";
import { api, Character, EstimateRequest, Location, PromptRevision, Scene, ScenePromptState } from "../../api";
import { EstimateLine, useConfirmedRun, useEstimate } from "../../estimate";
import { TextModelPicker, useTextModel } from "../../textmodel";

const REVISE_CHIPS = ["Pindahkan ke malam hari", "Tambah dialog", "Buat lebih singkat", "Buat lebih dramatis", "Ganti shot terakhir jadi close-up"];

/** Ubah prompt adegan dengan instruksi (plan 18 Revisi 10). AI merevisi prompt TERSIMPAN; hasilnya draf yang dibandingkan dulu. */
function PromptAi({ sceneId, locked, dirty, onApply }: { sceneId: string; locked: boolean; dirty: boolean; onApply: (prompt: string) => void }) {
  const tm = useTextModel("scene");
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [res, setRes] = useState<{ r: PromptRevision; asked: string } | null>(null);
  const body: EstimateRequest = { kind: "scene_prompt_revise", model: tm.model, scene_id: sceneId };
  const live = useEstimate(open && !dirty ? body : null);
  const run = useConfirmedRun(() => body, async (c) => {
    const r = await api.revisePrompt(sceneId, { model: tm.model, instruction: text.trim(), ...c });
    setRes({ r, asked: text.trim() });
    toast.success(`Revisi siap${r.cost != null ? ` ($${r.cost.toFixed(4)})` : ""}; periksa lalu terapkan`);
  });
  useEffect(() => { setRes(null); }, [sceneId]);
  if (!open) return <button type="button" className="btn sm" disabled={locked} onClick={() => setOpen(true)}><Bot size={13} /> Ubah dengan AI</button>;
  const lines = res ? res.r.prompt.split("\n") : [];
  const changed = new Set(res?.r.changed ?? []);
  return (
    <div className="v2-revise jr-card">
      <div className="v2-revise-head"><strong>Ubah adegan dengan AI</strong>
        <button type="button" className="btn ghost sm" aria-label="Tutup" onClick={() => { setOpen(false); setRes(null); }}>×</button></div>
      {dirty && <p className="warn">Simpan prompt adegan dulu; AI mengubah prompt yang tersimpan.</p>}
      <label className="field">Apa yang ingin diubah
        <textarea rows={2} maxLength={500} value={text} disabled={locked} placeholder="Contoh: pindahkan ke dapur dan tambah Sari di adegan ini" onChange={(e) => setText(e.target.value)} />
      </label>
      <span className="v2-presets">{REVISE_CHIPS.map((c) => <button key={c} type="button" className="chip preset" disabled={locked}
        onClick={() => setText((t) => (t ? `${t.replace(/[.\s]+$/, "")}. ${c}` : c))}>{c}</button>)}</span>
      <TextModelPicker task="scene" value={tm.model} onChange={tm.setModel} />
      <EstimateLine est={live.est} error={live.error} />
      {run.error && <p className="error">{run.error}</p>}
      <button type="button" className="btn primary" disabled={locked || dirty || !text.trim() || !!live.error || !live.est || !!live.est.blocked} onClick={() => void run.start()}>
        <Bot size={14} /> Minta revisi AI
      </button>
      {run.dialog}
      {res && (
        <div className="v2-diff" aria-live="polite">
          <h4>Hasil revisi: “{res.asked}”</h4>
          <p className="muted">{changed.size} baris berubah{res.r.attempts > 1 ? " · dicoba ulang sekali" : ""}</p>
          {res.r.warnings.length > 0 && <p className="warn">{res.r.warnings.slice(0, 3).join(" · ")}</p>}
          <pre className="v2-diff-pre">{lines.map((l, i) => <span key={i} className={changed.has(i + 1) ? "chg" : ""}>{l || " "}</span>)}</pre>
          <details><summary className="muted">Prompt sebelumnya</summary><pre className="old">{res.r.previous}</pre></details>
          <div className="actions">
            <button type="button" className="btn primary sm" onClick={() => { onApply(res.r.prompt); setRes(null); setOpen(false); }}>Terapkan ke editor</button>
            <button type="button" className="btn ghost sm" onClick={() => setRes(null)}>Buang</button>
          </div>
          <p className="muted">Belum tersimpan: periksa di editor lalu tekan Simpan prompt.</p>
        </div>
      )}
    </div>
  );
}

type Linked = { characters: { id: string; name: string; image_id?: string | null }[]; location: { id: string; name: string; image_id: string | null } | null };

export function ScenePromptEditor({ scene, characters, locations, locked, rows = 12, onSaved, onDirty }: {
  scene: Scene; characters: Character[]; locations: Location[]; locked: boolean; rows?: number;
  onSaved: () => void; onDirty?: (dirty: boolean) => void;
}) {
  const [state, setState] = useState<ScenePromptState | null>(null);
  const [text, setText] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [link, setLink] = useState<Linked | null>(null);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const base = useRef("");
  const ta = useRef<HTMLTextAreaElement>(null);
  const dirty = state !== null && text !== base.current;
  const dirtyRef = useRef(false);
  dirtyRef.current = dirty;

  const load = useCallback(async () => {
    try {
      const s = await api.scenePrompt(scene.id);
      setState(s); setText(s.prompt); base.current = s.prompt; setErrors(s.errors); setWarnings(s.warnings); setLoadError(null);
      setLink(s.assets);
    } catch (e) { setLoadError((e as Error).message); }
  }, [scene.id]);

  // muat saat adegan berganti atau data adegan berubah dari luar (editor Beat, revisi AI); teks yang sedang disunting tidak ditimpa
  useEffect(() => { if (!dirtyRef.current) void load(); }, [load, scene.updated_at]);
  useEffect(() => { onDirty?.(dirty); }, [dirty, onDirty]);

  // validasi hidup (tanpa menyimpan)
  useEffect(() => {
    if (!state || !dirty) return;
    const t = setTimeout(() => {
      api.checkScenePrompt(scene.id, text).then((r) => { setErrors(r.errors); setWarnings(r.warnings); if (r.will_link) setLink(r.will_link); })
        .catch((e: Error) => setErrors([e.message]));
    }, 600);
    return () => clearTimeout(t);
  }, [text, dirty, state, scene.id]);

  async function save() {
    setSaving(true);
    try {
      const s = await api.saveScenePrompt(scene.id, text);
      setState(s); setText(s.prompt); base.current = s.prompt; setErrors(s.errors); setWarnings(s.warnings); setLink(s.assets);
      toast.success("Prompt adegan tersimpan; latar, pemeran, dan beat mengikuti");
      onSaved();
    } catch (e) { setErrors([(e as Error).message]); toast.error((e as Error).message); }
    finally { setSaving(false); }
  }
  useEffect(() => {   // Ctrl/Cmd+S saat fokus di editor ini
    const el = ta.current;
    if (!el) return;
    const on = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); if (dirtyRef.current && !locked) void save(); } };
    el.addEventListener("keydown", on);
    return () => el.removeEventListener("keydown", on);
  });   // eslint-disable-line react-hooks/exhaustive-deps

  const insert = (s: string) => {
    const el = ta.current;
    const at = el ? [el.selectionStart, el.selectionEnd] : [text.length, text.length];
    setText(text.slice(0, at[0]) + s + text.slice(at[1]));
    requestAnimationFrame(() => { if (el) { el.focus(); el.setSelectionRange(at[0] + s.length, at[0] + s.length); } });
  };

  if (loadError) return <p className="error"><AlertTriangle size={14} /> {loadError}</p>;
  if (!state) return <p className="muted"><Loader2 size={14} className="spin" /> Memuat prompt adegan…</p>;
  const chars = link?.characters ?? [];
  const loc = link?.location ?? null;
  return (
    <div className="v2-sp">
      <label className="field">Prompt adegan
        <textarea ref={ta} rows={rows} maxLength={4000} value={text} disabled={locked} spellCheck={false} onChange={(e) => setText(e.target.value)}
          aria-invalid={errors.length > 0} aria-label="Prompt adegan" />
      </label>
      <div className="v2-insert" aria-label="Sisipkan mention">
        <span className="muted">Sisipkan:</span>
        {characters.map((c) => <button key={c.id} type="button" className="chip mention character" disabled={locked} onClick={() => insert(`@[${c.name}]`)}>@{c.name}</button>)}
        {locations.map((l) => <button key={l.id} type="button" className="chip mention location" disabled={locked} onClick={() => insert(`#[${l.name}]`)}>#{l.name}</button>)}
      </div>

      {errors.map((e) => <p key={e} className="error" role="alert"><AlertTriangle size={13} /> {e}</p>)}
      {warnings.map((w) => <p key={w} className="warn"><ImageOff size={13} /> {w}</p>)}

      <div className="v2-assets" aria-label="Aset yang terhubung">
        <span className="muted">{dirty ? "Akan terhubung" : "Terhubung"}:</span>
        {chars.length === 0 && !loc && <span className="muted">belum ada karakter atau latar yang disebut</span>}
        {chars.map((c) => (
          <span key={c.id} className="v2-asset">{c.image_id ? <img src={api.imageUrl(c.image_id)} alt="" /> : <ImageOff size={14} />}@{c.name}</span>
        ))}
        {loc && <span className="v2-asset">{loc.image_id ? <img src={api.imageUrl(loc.image_id)} alt="" /> : <ImageOff size={14} />}#{loc.name}</span>}
      </div>

      <div className="v2-prompt-foot">
        <span className="muted">{text.length}/4000 · {dirty ? "belum disimpan" : state.derived ? "dirender dari data adegan; simpan untuk mengunci teksnya" : "tersimpan"}</span>
        {dirty && <button type="button" className="btn ghost sm" onClick={() => { setText(base.current); setErrors(state.errors); setWarnings(state.warnings); setLink(state.assets); }}>Batalkan perubahan</button>}
        <button type="button" className="btn primary sm" disabled={locked || !dirty || saving || errors.length > 0} onClick={() => void save()}>
          {saving ? <Loader2 size={13} className="spin" /> : <Save size={13} />} Simpan prompt
        </button>
      </div>
      <p className="muted">Latar, pemeran, beat, mood, dan durasi adegan diturunkan dari prompt ini. Ubah di sini saja.</p>
      <PromptAi sceneId={scene.id} locked={locked} dirty={dirty} onApply={(p) => setText(p)} />
    </div>
  );
}
