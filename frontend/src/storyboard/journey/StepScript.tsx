// Langkah 2 alur episode: naskah utuh dengan mention @[karakter] / #[latar] (plan 15).
import { useEffect, useRef, useState } from "react";
import { Bot, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { api, Character, EstimateRequest, JourneyState, Location, ScriptRevision } from "../../api";
import { EstimateLine, useConfirmedRun, useEstimate } from "../../estimate";
import { SaveText } from "../fields";
import { TextModelPicker, useTextModel } from "../../textmodel";
import { key, openToken, pieces } from "./mentions";

const MAX = 20000;
type Sug = { sign: "@" | "#"; start: number; items: { id: string; name: string }[]; index: number };

export function StepScript({ filmId, synopsis, journey, characters, locations, locked, reload, saveSynopsis }: {
  filmId: string; synopsis: string; journey: JourneyState; characters: Character[]; locations: Location[]; locked: boolean;
  reload: () => Promise<unknown>; saveSynopsis: (v: string) => Promise<unknown>;
}) {
  const [text, setText] = useState(journey.script);
  const [saving, setSaving] = useState(false);
  const [sug, setSug] = useState<Sug | null>(null);
  const [draft, setDraft] = useState<{ script: string; warnings: string[] } | null>(null);
  const ta = useRef<HTMLTextAreaElement>(null);
  const saved = useRef(journey.script);
  useEffect(() => { setText(journey.script); saved.current = journey.script; setDraft(null); }, [filmId]);   // eslint-disable-line react-hooks/exhaustive-deps

  async function flush(value: string) {
    if (value === saved.current) return;
    setSaving(true);
    try { await api.updateFilm(filmId, { script: value }); saved.current = value; await reload(); }
    catch (e) { toast.error((e as Error).message); }
    finally { setSaving(false); }
  }
  useEffect(() => {   // simpan otomatis 0,9 dtk setelah berhenti mengetik
    if (text === saved.current || locked) return;
    const t = setTimeout(() => void flush(text), 900);
    return () => clearTimeout(t);
  }, [text]);   // eslint-disable-line react-hooks/exhaustive-deps

  function onChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const v = e.target.value;
    setText(v);
    const tok = openToken(v, e.target.selectionStart);
    if (!tok) return setSug(null);
    const pool = tok.sign === "@" ? journey.characters : journey.locations;
    const q = key(tok.query);
    const items = pool.filter((p) => key(p.name).includes(q)).slice(0, 6);
    setSug(items.length ? { sign: tok.sign, start: tok.start, items, index: 0 } : null);
  }
  function place(insert: string, from: number, to: number) {
    const next = text.slice(0, from) + insert + text.slice(to);
    setText(next); setSug(null);
    requestAnimationFrame(() => { const el = ta.current; if (el) { el.focus(); el.setSelectionRange(from + insert.length, from + insert.length); } });
  }
  const accept = (s: Sug, i: number) => place(`${s.sign}[${s.items[i].name}]`, s.start, ta.current!.selectionStart);
  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (!sug) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); setSug({ ...sug, index: (sug.index + (e.key === "ArrowDown" ? 1 : sug.items.length - 1)) % sug.items.length }); }
    else if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); accept(sug, sug.index); }
    else if (e.key === "Escape") { e.preventDefault(); setSug(null); }
  }
  const insertAtCaret = (s: string) => { const el = ta.current!; place(s, el.selectionStart, el.selectionEnd); };

  // pratinjau berwarna + mention yang belum ada di episode
  const inEp = { character: new Set(journey.characters.map((c) => key(c.name))), location: new Set(journey.locations.map((l) => key(l.name))) };
  async function addToEpisode(kind: "character" | "location", name: string) {
    const found = (kind === "character" ? characters : locations).find((x) => key(x.name) === key(name));
    if (!found) return void toast.error(`"${name}" belum ada di workspace; buat dulu di ${kind === "character" ? "halaman Karakter" : "tab Latar"}`);
    try {
      await api.setEpisodeCast(filmId, {
        character_ids: [...journey.characters.map((c) => c.id), ...(kind === "character" ? [found.id] : [])],
        location_ids: [...journey.locations.map((l) => l.id), ...(kind === "location" ? [found.id] : [])],
      });
      await reload();
    } catch (e) { toast.error((e as Error).message); }
  }

  // AI: bantu tulis naskah (berbayar kecil; hasil berupa draf)
  const tm = useTextModel("script");
  const body: (EstimateRequest & { v?: string }) = { kind: "episode_script", model: tm.model, film_id: filmId, v: `${synopsis.length}:${text.trim() ? 1 : 0}:${journey.characters.length}` };
  const live = useEstimate(body);
  const ai = useConfirmedRun(() => body, async (c) => {
    if (text !== saved.current) await flush(text);
    const r = await api.scriptDraft(filmId, { model: tm.model, ...c });
    setDraft({ script: r.script, warnings: r.warnings });
    toast.success(`Draf naskah siap${r.cost != null ? ` ($${r.cost.toFixed(4)})` : ""}`);
  });
  const useDraft = (mode: "replace" | "append") => {
    if (!draft) return;
    if (mode === "replace" && text.trim() && !window.confirm("Ganti naskah yang sekarang dengan draf AI?")) return;
    const next = (mode === "replace" ? draft.script : `${text.trimEnd()}\n\n${draft.script}`).slice(0, MAX);
    setText(next); setDraft(null);
  };

  // ---- ubah naskah dengan instruksi (plan 18 Revisi 7) ----
  const REVISE_CHIPS = ["Ubah suasana adegan terakhir jadi malam hari", "Tambah adegan penutup", "Buat semua adegan lebih singkat", "Tambah dialog"];
  const [instruction, setInstruction] = useState("");
  const [rev, setRev] = useState<{ r: ScriptRevision; asked: string; base: string } | null>(null);
  const [before, setBefore] = useState<string | null>(null);   // naskah sebelum revisi diterapkan (untuk dikembalikan)
  const reviseBody: EstimateRequest & { v?: string } = { kind: "script_revise", model: tm.model, film_id: filmId, v: String(saved.current.length) };
  const reviseLive = useEstimate(text.trim() ? reviseBody : null);
  const revise = useConfirmedRun(() => reviseBody, async (c) => {
    if (text !== saved.current) await flush(text);
    const base = saved.current;
    const r = await api.reviseScript(filmId, { model: tm.model, instruction: instruction.trim(), ...c });
    setRev({ r, asked: instruction.trim(), base });
    toast.success(`Revisi siap${r.cost != null ? ` ($${r.cost.toFixed(4)})` : ""}; periksa lalu terapkan`);
  });
  const applyRevision = () => {
    if (!rev) return;
    if (text !== rev.base && !window.confirm("Naskah berubah sejak revisi diminta; menerapkan akan menimpa perubahan itu. Lanjutkan?")) return;
    setBefore(text); setText(rev.r.script.slice(0, MAX)); setRev(null);
    toast.success("Revisi diterapkan dan disimpan otomatis. Bisa dikembalikan dari tombol di bawah.");
  };
  const changedCount = rev?.r.scenes.filter((s) => s.changed).length ?? 0;

  return (
    <div className="jr-script">
      <div className="jr-card">
        <h3>Sinopsis</h3>
        <SaveText label="Sinopsis" multiline rows={2} value={synopsis} maxLength={2000} placeholder="Ringkasan cerita episode ini (dipakai AI untuk menulis naskah)"
          onSave={(v) => saveSynopsis(v)} />
      </div>
      <div className="jr-card">
        <div className="jr-toolbar">
          <h3>Naskah</h3>
          <span className="muted">{saving ? "Menyimpan…" : text === saved.current ? "Tersimpan" : "Belum disimpan"} · {text.length.toLocaleString("id-ID")}/{MAX.toLocaleString("id-ID")}</span>
        </div>
        <div className="jr-insert" aria-label="Sisipkan mention">
          <span className="muted">Sisipkan:</span>
          {journey.characters.map((c) => <button key={c.id} className="chip mention character" disabled={locked} onClick={() => insertAtCaret(`@[${c.name}]`)}>@{c.name}</button>)}
          {journey.locations.map((l) => <button key={l.id} className="chip mention location" disabled={locked} onClick={() => insertAtCaret(`#[${l.name}]`)}>#{l.name}</button>)}
          {journey.characters.length + journey.locations.length === 0 && <span className="muted">Pilih karakter dan latar di langkah 1 dulu.</span>}
        </div>
        <div className="jr-editor">
          <textarea ref={ta} value={text} onChange={onChange} onKeyDown={onKeyDown} onBlur={() => { setSug(null); void flush(text); }} disabled={locked}
            maxLength={MAX} rows={14} aria-label="Naskah episode"
            placeholder={"Tulis ceritanya. Ketik @ untuk menyebut karakter dan # untuk latar, mis.\n#[Warung kopi] senja. @[Rani] masuk dan menyapa @[Budi]."} />
          {sug && (
            <ul className="jr-sug" role="listbox" aria-label="Saran mention">
              {sug.items.map((it, i) => (
                <li key={it.id} role="option" aria-selected={i === sug.index} className={i === sug.index ? "on" : ""}
                  onMouseDown={(e) => { e.preventDefault(); accept(sug, i); }}>{sug.sign}{it.name}</li>
              ))}
            </ul>
          )}
        </div>
        {journey.format.detected && (
          <p className={journey.format.errors.length ? "error" : "muted"} role="status">
            {journey.format.errors.length
              ? <>Format shot Seedance: ada masalah. {journey.format.errors.slice(0, 3).join(" · ")}</>
              : <>Format shot Seedance terbaca: {journey.format.scenes} adegan, {journey.format.shots} shot. Buat adegan dan beat-nya gratis di langkah Adegan.</>}
          </p>
        )}
        {(journey.mentions.unknown.length > 0 || journey.mentions.ambiguous.length > 0) && (
          <div className="jr-issues">
            {journey.mentions.unknown.map((u) => (
              <span key={u.kind + u.name} className="warn">
                {u.kind === "character" ? "@" : "#"}{u.name} belum ada di episode{" "}
                <button className="btn ghost sm" disabled={locked} onClick={() => void addToEpisode(u.kind, u.name)}>tambahkan</button>
              </span>
            ))}
            {journey.mentions.ambiguous.map((a) => <span key={a.kind + a.name} className="error">"{a.name}" bernama ganda di episode; ganti salah satu namanya.</span>)}
          </div>
        )}
        {text.trim() && (
          <details className="jr-preview" open>
            <summary>Pratinjau</summary>
            <p>{pieces(text).map((p, i) => "text" in p ? <span key={i}>{p.text}</span>
              : <span key={i} className={`mention ${p.kind} ${inEp[p.kind].has(key(p.name)) ? "" : "unknown"}`}>{p.kind === "character" ? "@" : "#"}{p.name}</span>)}</p>
          </details>
        )}
      </div>
      <div className="jr-card">
        <h3><Bot size={14} /> Bantu tulis dengan AI</h3>
        <p className="muted">AI menulis dari sinopsis, karakter, dan latar episode. Hasilnya draf yang kamu periksa dulu.</p>
        <TextModelPicker task="script" value={tm.model} onChange={tm.setModel} />
        <EstimateLine est={live.est} error={live.error} />
        {ai.error && <p className="error">{ai.error}</p>}
        <button className="btn" disabled={locked || !!live.error || !live.est || !!live.est.blocked} onClick={() => void ai.start()}>
          <Bot size={14} /> {text.trim() ? "Tulis ulang / perbaiki dengan AI" : "Tulis naskah dengan AI"}
        </button>
        {draft && (
          <div className="jr-draft">
            <h4>Draf AI {draft.warnings.map((w) => <span key={w} className="warn"> · {w}</span>)}</h4>
            <pre>{draft.script}</pre>
            <div className="actions">
              <button className="btn primary sm" onClick={() => useDraft("replace")}>Ganti naskah</button>
              <button className="btn sm" onClick={() => useDraft("append")}>Tambahkan di akhir</button>
              <button className="btn ghost sm" onClick={() => setDraft(null)}>Buang</button>
            </div>
          </div>
        )}
        {ai.dialog}
      </div>
      {text.trim() && (
        <div className="jr-card v2-revise">
          <h3><Bot size={14} /> Ubah naskah dengan AI</h3>
          <p className="muted">Tulis apa yang ingin diubah; AI mengembalikan naskah berformat Seedance dan adegan yang tidak disentuh dipertahankan. Naskah dikirim utuh, jadi biayanya mengikuti panjang naskah.</p>
          <label className="field">Apa yang ingin diubah
            <textarea rows={2} maxLength={500} value={instruction} disabled={locked} placeholder="Contoh: ubah adegan 3 jadi malam hari dan tambah dialog Momon yang lapar"
              onChange={(e) => setInstruction(e.target.value)} />
          </label>
          <span className="v2-presets">{REVISE_CHIPS.map((c) => <button key={c} type="button" className="chip preset" disabled={locked}
            onClick={() => setInstruction((t) => (t ? `${t.replace(/[.\s]+$/, "")}. ${c}` : c))}>{c}</button>)}</span>
          <EstimateLine est={reviseLive.est} error={reviseLive.error} />
          {revise.error && <p className="error">{revise.error}</p>}
          <button className="btn primary" disabled={locked || !instruction.trim() || !!reviseLive.error || !reviseLive.est || !!reviseLive.est.blocked} onClick={() => void revise.start()}>
            <Bot size={14} /> Minta revisi AI
          </button>
          {revise.dialog}
          {rev && (
            <div className="v2-diff" aria-live="polite">
              <h4>Hasil revisi: “{rev.asked}”</h4>
              <p className="muted">{changedCount} dari {rev.r.scenes.length} adegan berubah{rev.r.removed > 0 ? ` · ${rev.r.removed} adegan lama dihapus` : ""}{!rev.r.format_before ? " · naskah prosa diubah ke format" : ""}</p>
              {rev.r.warnings.length > 0 && <p className="warn">{rev.r.warnings.slice(0, 4).join(" · ")}</p>}
              <ol className="v2-diff-list">
                {rev.r.scenes.map((s) => (
                  <li key={s.n} className={s.changed ? "chg" : ""}>
                    <details open={s.changed}>
                      <summary>Adegan {s.n} {s.changed ? <span className="chip meta">{s.previous ? "diubah" : "baru"}</span> : <span className="muted">tidak berubah</span>}</summary>
                      <pre>{s.text}</pre>
                      {s.previous && <details><summary className="muted">Versi sebelumnya</summary><pre className="old">{s.previous}</pre></details>}
                    </details>
                  </li>
                ))}
              </ol>
              <div className="actions">
                <button className="btn primary sm" onClick={applyRevision}>Terapkan ke naskah</button>
                <button className="btn ghost sm" onClick={() => setRev(null)}>Buang</button>
              </div>
              <p className="muted">Adegan dan beat yang sudah dibuat tidak otomatis berubah; buat ulang dari format di langkah Adegan, atau ubah per adegan di langkah Beat.</p>
            </div>
          )}
          {before !== null && !rev && (
            <button className="btn ghost sm" onClick={() => { setText(before); setBefore(null); }}><Undo2 size={13} /> Kembalikan naskah sebelum revisi</button>
          )}
        </div>
      )}
    </div>
  );
}
