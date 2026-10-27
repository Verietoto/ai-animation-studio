// Langkah "Beat" Storyboard v2 (plan 18): bagi tiap adegan jadi ketukan berdurasi. Jalur waktu dengan batas yang bisa diseret
// adalah elemen utamanya; sisanya sengaja tenang. Beat disunting sebagai daftar durasi (beatMath.ts) sehingga selalu bersambung.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bot, Clock, History, Loader2, Merge, Plus, Save, Scissors, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { api, BeatRevision, BeatsResponse, BeatVersion, EstimateRequest, FilmDetail, Scene } from "../../api";
import { EstimateLine, useConfirmedRun, useEstimate } from "../../estimate";
import { TextModelPicker, useTextModel } from "../../textmodel";
import {
  BeatDraft, blank, equalSplit, fromServer, mergeNext, moveBoundary, MIN_BEAT, r1, resizeWithin, scaleTo, signature, splitAt, starts, STEP, toPayload, total,
} from "./beatMath";

const HUES = [265, 190, 150, 35, 330, 215];
const hue = (scene: Scene, characterId: string) => HUES[Math.max(0, scene.cast.findIndex((c) => c.character_id === characterId)) % HUES.length];
const tint = (h: number, a = 0.22) => `hsla(${h}, 70%, 60%, ${a})`;
const CAMERA_PRESETS = ["Close-up", "Medium shot", "Wide shot", "Dolly in", "Pan kanan", "Tracking", "Handheld", "Dari atas"];
const SIZES = ["WS", "MS", "MCU", "CU", "ECU"];
const LENSES = ["24", "35", "50", "85"];
const WORDS_PER_SECOND = 3;
const MAX_SHOT = 3;   // format Seedance menganjurkan shot 1-3 dtk (server hanya memberi peringatan)
const fmt = (s: number) => `${r1(s)} dtk`;
const hasContent = (d: BeatDraft[]) => d.some((b) => b.action || b.camera || b.cast.length || b.dialogue.length);

const REVISE_CHIPS = ["Ubah suasana jadi malam hari", "Tambah dialog", "Buat lebih singkat", "Buat lebih dramatis", "Ganti shot terakhir jadi close-up"];

/** Ubah adegan yang sudah ada dengan instruksi bebas (plan 18 Revisi 6). Hasilnya draf yang dibandingkan dulu; baru masuk editor saat diterapkan. */
function RevisePanel({ scene, before, locked, dirty, onApply }: {
  scene: Scene; before: BeatDraft[]; locked: boolean; dirty: boolean; onApply: (r: BeatRevision, instruction: string) => void;
}) {
  const tm = useTextModel("scene");
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [res, setRes] = useState<BeatRevision | null>(null);
  const [asked, setAsked] = useState("");
  const body: EstimateRequest = { kind: "scene_revise", model: tm.model, scene_id: scene.id };
  const live = useEstimate(open ? body : null);
  const run = useConfirmedRun(() => body, async (c) => {
    const r = await api.reviseScene(scene.id, { model: tm.model, instruction: text.trim(), ...c });
    setRes(r); setAsked(text.trim());
    toast.success(`Revisi siap${r.cost != null ? ` ($${r.cost.toFixed(4)})` : ""}; periksa lalu terapkan`);
  });
  const changed = res?.beats.filter((b) => b.changed).length ?? 0;
  useEffect(() => { setRes(null); }, [scene.id]);

  if (!open) return <button className="btn sm" disabled={locked || before.length === 0} title={before.length ? undefined : "Buat beat dulu"} onClick={() => setOpen(true)}><Bot size={13} /> Ubah dengan AI</button>;
  return (
    <div className="v2-revise jr-card">
      <div className="v2-revise-head"><strong>Ubah adegan {scene.number} dengan AI</strong><button className="btn ghost sm" onClick={() => { setOpen(false); setRes(null); }} aria-label="Tutup"><X size={13} /></button></div>
      <label className="field">Apa yang ingin diubah
        <textarea rows={2} maxLength={500} value={text} placeholder="Contoh: ubah jadi malam hari dan tambah dialog Momon yang lapar" onChange={(e) => setText(e.target.value)} />
      </label>
      <span className="v2-presets">{REVISE_CHIPS.map((c) => <button key={c} type="button" className="chip preset" onClick={() => setText((t) => (t ? `${t.replace(/[.\s]+$/, "")}. ${c}` : c))}>{c}</button>)}</span>
      <TextModelPicker task="scene" value={tm.model} onChange={tm.setModel} />
      <EstimateLine est={live.est} error={live.error} />
      {run.error && <p className="error">{run.error}</p>}
      <button className="btn primary" disabled={locked || !text.trim() || !!live.error || !live.est || !!live.est.blocked} onClick={() => void run.start()}>Minta revisi AI</button>
      {run.dialog}
      {res && (
        <div className="v2-diff" aria-live="polite">
          <h4>Hasil revisi: “{asked}”</h4>
          <p className="muted">{changed} dari {res.beats.length} shot berubah · {fmt(res.previous_seconds)} → {fmt(res.total_seconds)}
            {res.mood_changed && <> · mood: {res.mood || "(kosong)"}</>}{res.time_changed && <> · waktu: {res.time_of_day || "(kosong)"}</>}</p>
          {res.warnings.length > 0 && <p className="warn">{res.warnings.slice(0, 3).join(" · ")}</p>}
          <ol className="v2-diff-list">
            {res.beats.map((b, i) => {
              const old = b.from ? before[b.from - 1] : null;
              return (
                <li key={b.id} className={b.changed ? "chg" : ""}>
                  <span className="muted">{r1(b.start)}–{r1(b.end)} dtk · {b.size ?? "-"} {b.lens ? `${b.lens}mm` : ""} · {b.camera || "-"}</span>
                  <div>{b.action || <i className="muted">(tanpa aksi)</i>}{b.dialogue.map((d, k) => <em key={k}> “{d.text}”</em>)}</div>
                  {b.changed && old && old.action !== b.action && <div className="muted old">sebelumnya: {old.action || "(kosong)"}</div>}
                  {b.changed && !b.from && <span className="chip meta">baru</span>}
                  {b.changed && b.from && <span className="chip meta">diubah{b.from !== i + 1 ? ` (dari shot ${b.from})` : ""}</span>}
                </li>
              );
            })}
          </ol>
          {before.length > res.beats.length && <p className="muted">{before.length - res.beats.length} shot lama dihapus.</p>}
          <div className="actions">
            <button className="btn primary sm" onClick={() => {
              if (dirty && !window.confirm("Ada perubahan yang belum disimpan di adegan ini; menerapkan revisi akan menimpanya. Lanjutkan?")) return;
              onApply(res, asked); setRes(null); setOpen(false);
            }}>Terapkan ke editor</button>
            <button className="btn ghost sm" onClick={() => setRes(null)}>Buang</button>
          </div>
          <p className="muted">Belum tersimpan: tekan Simpan. Versi lama tetap bisa dikembalikan dari Versi.</p>
        </div>
      )}
    </div>
  );
}

/** AI membuat shot sesuai format prompt Seedance 2.0 (plan 18 Revisi 4); hasilnya draf yang belum tersimpan. */
function AiShots({ scene, locked, hasContent, onDraft }: { scene: Scene; locked: boolean; hasContent: boolean; onDraft: (res: Awaited<ReturnType<typeof api.aiBeats>>) => void }) {
  const tm = useTextModel("scene");
  const body: EstimateRequest = { kind: "scene_beats", model: tm.model, scene_id: scene.id };
  const live = useEstimate(body);
  const run = useConfirmedRun(() => body, async (c) => {
    const res = await api.aiBeats(scene.id, { model: tm.model, ...c });
    onDraft(res);
    toast.success(`AI membuat ${res.beats.length} shot${res.cost != null ? ` ($${res.cost.toFixed(4)})` : ""}; periksa lalu simpan`);
  });
  return (
    <div className="v2-ai">
      <TextModelPicker task="scene" value={tm.model} onChange={tm.setModel} />
      <EstimateLine est={live.est} error={live.error} />
      {run.error && <p className="error">{run.error}</p>}
      <button className="btn primary" disabled={locked || !!live.error || !live.est || !!live.est.blocked}
        onClick={() => { if (!hasContent || window.confirm("AI akan mengganti semua beat adegan ini (belum tersimpan sampai Anda simpan). Lanjutkan?")) void run.start(); }}>
        Buat shot dengan AI
      </button>
      {run.dialog}
    </div>
  );
}

interface ScenePatch { extra_prompt?: string; time_of_day?: string; planned_seconds?: number }
interface Entry { d: BeatDraft[]; sig: string; warnings: string[]; patch?: ScenePatch; note?: string }
type Store = Record<string, Entry>;

export function BeatEditor({ detail, locked, onChanged, goScenes }: { detail: FilmDetail; locked: boolean; onChanged: () => void; goScenes: () => void }) {
  const scenes = detail.scenes;
  const [sceneId, setSceneId] = useState<string | null>(scenes[0]?.id ?? null);
  const [store, setStore] = useState<Store>({});
  const [sel, setSel] = useState(0);
  const [saving, setSaving] = useState(false);
  const [versions, setVersions] = useState<BeatVersion[] | null>(null);
  const laneRef = useRef<HTMLDivElement>(null);
  const storeRef = useRef(store);
  storeRef.current = store;

  const scene = scenes.find((s) => s.id === sceneId) ?? null;
  const entry = sceneId ? store[sceneId] : undefined;
  const beats = entry?.d ?? [];
  const dirty = (e?: Entry) => !!e && (signature(e.d) !== e.sig || !!e.patch);
  const dirtyCount = Object.values(store).filter((e) => dirty(e)).length;
  const totalSec = total(beats);
  const planned = scene?.planned_seconds ?? null;
  const mismatch = planned != null && beats.length > 0 && Math.abs(totalSec - planned) > 0.05;

  const put = useCallback((id: string, res: BeatsResponse) => {
    const d = fromServer(res.beats);
    setStore((s) => ({ ...s, [id]: { d, sig: signature(d), warnings: [...res.warnings, ...(res.warnings_save ?? [])] } }));
  }, []);

  // muat beat semua adegan sekali (untuk rel adegan); adegan baru yang muncul ikut dimuat
  useEffect(() => {
    for (const s of scenes) {
      if (storeRef.current[s.id]) continue;
      void api.beats(s.id).then((res) => { if (!storeRef.current[s.id]) put(s.id, res); }).catch((e: Error) => toast.error(e.message));
    }
    if (!sceneId && scenes[0]) setSceneId(scenes[0].id);
  }, [scenes, sceneId, put]);
  useEffect(() => { setSel(0); setVersions(null); }, [sceneId]);

  const setBeats = (next: BeatDraft[] | null, failMsg?: string) => {
    if (!next) { if (failMsg) toast.error(failMsg); return; }
    if (!sceneId) return;
    setStore((s) => ({ ...s, [sceneId]: { ...(s[sceneId] ?? { sig: "", warnings: [] }), d: next } }));
  };
  const patchBeat = (i: number, p: Partial<BeatDraft>) => setBeats(beats.map((b, n) => (n === i ? { ...b, ...p } : b)));

  const save = useCallback(async (id: string, note = ""): Promise<boolean> => {
    const e = storeRef.current[id];
    if (!e) return true;
    try {
      const res = await api.saveBeats(id, toPayload(e.d), note || e.note || "");
      if (e.patch) await api.updateScene(id, e.patch);   // mood/waktu/durasi dari revisi AI baru masuk ke adegan saat disimpan
      put(id, res); onChanged(); return true;
    }
    catch (err) { toast.error((err as Error).message); return false; }
  }, [put, onChanged]);

  async function saveCurrent() {
    if (!sceneId) return;
    setSaving(true);
    const ok = await save(sceneId);
    setSaving(false);
    if (ok) toast.success("Beat tersimpan");
  }
  async function saveAll() {
    setSaving(true);
    let n = 0;
    for (const [id, e] of Object.entries(storeRef.current)) if (dirty(e) && await save(id)) n++;
    setSaving(false);
    if (n) toast.success(`${n} adegan tersimpan`);
  }
  useEffect(() => {   // Ctrl/Cmd+S
    const onKey = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); void saveAll(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  useEffect(() => () => {   // keluar dari langkah ini: simpan yang belum tersimpan, jangan buang diam-diam
    for (const [id, e] of Object.entries(storeRef.current)) if (dirty(e)) void api.saveBeats(id, toPayload(e.d), e.note || "otomatis saat pindah langkah").then(() => (e.patch ? api.updateScene(id, e.patch) : null))
      .then(() => toast.success("Beat tersimpan otomatis")).catch((err: Error) => toast.error(`Beat adegan belum tersimpan: ${err.message}`));
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  // ---- seret batas antar beat ----
  function dragBoundary(e: React.PointerEvent, i: number) {
    if (locked || !laneRef.current) return;
    e.preventDefault();
    const base = beats, startLeft = beats[i].dur, startX = e.clientX;
    const pxPerSec = laneRef.current.clientWidth / (totalSec || 1);
    const move = (ev: PointerEvent) => setBeats(moveBoundary(base, i, startLeft + (ev.clientX - startX) / pxPerSec) ?? base);
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  }
  const nudgeBoundary = (e: React.KeyboardEvent, i: number) => {
    if (e.key === "ArrowLeft") { e.preventDefault(); setBeats(moveBoundary(beats, i, beats[i].dur - STEP)); }
    if (e.key === "ArrowRight") { e.preventDefault(); setBeats(moveBoundary(beats, i, beats[i].dur + STEP)); }
  };

  // ---- aksi susunan ----
  const startEmpty = (n: number) => setBeats(equalSplit(planned ?? 8, n));
  const redistribute = (n: number) => {
    if (hasContent(beats) && !window.confirm("Bagi rata akan membuat beat baru dan mengosongkan isi beat sekarang. Lanjutkan?")) return;
    setBeats(equalSplit(totalSec || planned || 8, n)); setSel(0);
  };
  const applyDraft = (res: Awaited<ReturnType<typeof api.aiBeats>>) => {
    setBeats(fromServer(res.beats).map((b) => ({ ...b, id: undefined, key: blank(0).key })));   // draf: id server belum ada
    setSel(0);
    if (res.warnings.length) toast.warning(res.warnings.slice(0, 3).join(" · "));
  };
  const applyRevision = (r: BeatRevision, instruction: string) => {
    if (!sceneId) return;
    const patch: ScenePatch = {
      ...(r.mood_changed ? { extra_prompt: r.mood } : {}), ...(r.time_changed ? { time_of_day: r.time_of_day } : {}),
      ...(Math.abs(r.total_seconds - r.previous_seconds) > 0.05 ? { planned_seconds: Math.ceil(r.total_seconds - 1e-9) } : {}),
    };
    setStore((s) => ({ ...s, [sceneId]: { ...(s[sceneId] ?? { sig: "", warnings: [] }), d: fromServer(r.beats), note: `AI: ${instruction}`.slice(0, 200),
      patch: Object.keys(patch).length ? patch : undefined } }));
    setSel(0);
    if (r.warnings.length) toast.warning(r.warnings.slice(0, 3).join(" · "));
  };
  const addAtEnd = () => { setBeats([...beats, blank(2)]); setSel(beats.length); };
  const remove = (i: number) => {
    if (beats.length <= 1) return;
    const gone = beats[i];
    if (hasContent([gone]) && !window.confirm(`Hapus beat ${i + 1}? Isinya ikut hilang (bisa dikembalikan dari Versi setelah disimpan).`)) return;
    const rest = beats.filter((_, n) => n !== i);
    const j = Math.min(i, rest.length - 1);   // waktu beat yang dihapus diberikan ke tetangganya agar total tetap
    rest[j] = { ...rest[j], dur: r1(rest[j].dur + gone.dur) };
    setBeats(rest); setSel(Math.min(sel, rest.length - 1));
  };

  async function openVersions() {
    if (!sceneId) return;
    try { setVersions(await api.beatVersions(sceneId)); } catch (e) { toast.error((e as Error).message); }
  }
  async function restore(v: BeatVersion) {
    if (!sceneId) return;
    if (dirty(entry) && !window.confirm("Ada perubahan yang belum disimpan di adegan ini; memulihkan versi akan menimpanya. Lanjutkan?")) return;
    try { put(sceneId, await api.restoreBeats(sceneId, v.id)); setVersions(null); onChanged(); toast.success("Versi dipulihkan"); }
    catch (e) { toast.error((e as Error).message); }
  }
  async function setPlanned(sec: number) {
    if (!scene) return;
    try { await api.updateScene(scene.id, { planned_seconds: Math.max(1, Math.round(sec)) }); onChanged(); }
    catch (e) { toast.error((e as Error).message); }
  }

  const b = beats[sel] ?? null;
  const at = useMemo(() => starts(beats), [beats]);

  if (!scenes.length) {
    return (
      <div className="empty">
        <Clock size={32} /><strong>Belum ada adegan</strong>
        <span className="muted">Beat membagi waktu di dalam adegan. Buat adegannya dulu.</span>
        <button className="btn primary" onClick={goScenes}>Ke langkah Adegan</button>
      </div>
    );
  }

  return (
    <div className="v2-beats">
      <nav className="v2-rail" aria-label="Adegan">
        {scenes.map((s) => {
          const e = store[s.id];
          const sum = e ? total(e.d) : 0;
          return (
            <button key={s.id} className={`v2-rail-item ${s.id === sceneId ? "on" : ""}`} onClick={() => setSceneId(s.id)} aria-current={s.id === sceneId ? "true" : undefined}>
              <span className="v2-rail-title"><strong>Adegan {s.number}</strong>{dirty(e) && <span className="v2-dot" title="Belum disimpan" />}</span>
              <span className="muted clamp1">{s.location?.name ?? "tanpa latar"}</span>
              <span className="v2-mini" aria-hidden>
                {e?.d.length ? e.d.map((x) => <i key={x.key} style={{ flex: x.dur }} />) : <i className="empty" />}
              </span>
              <span className="muted">{e ? `${e.d.length} beat · ${fmt(sum)}` : "memuat…"}</span>
            </button>
          );
        })}
      </nav>

      <section className="v2-editor" aria-label={scene ? `Beat adegan ${scene.number}` : "Beat"}>
        {scene && entry && (<>
          <header className="v2-ed-head">
            <h3>Adegan {scene.number}{scene.location ? ` · ${scene.location.name}` : ""}</h3>
            <label className="v2-dur">Durasi adegan
              <input type="number" min={1} step={1} placeholder="—" disabled={locked} aria-label="Durasi adegan (detik)"
                key={`${scene.id}:${planned ?? ""}`} defaultValue={planned ?? ""}
                onBlur={(e) => { const v = e.target.valueAsNumber; if (Number.isFinite(v) && v !== planned) void setPlanned(v); }} /> dtk
            </label>
            <div className="v2-ed-actions">
              <button className="btn ghost sm" onClick={() => void openVersions()} disabled={locked}><History size={14} /> Versi</button>
              <button className="btn primary sm" disabled={saving || locked || dirtyCount === 0} onClick={() => void (dirtyCount > 1 ? saveAll() : saveCurrent())}>
                {saving ? <Loader2 size={14} className="spin" /> : <Save size={14} />} {dirtyCount > 1 ? `Simpan ${dirtyCount} adegan` : dirtyCount === 1 ? "Simpan beat" : "Tersimpan"}
              </button>
            </div>
          </header>

          {versions && (
            <div className="v2-pop" role="dialog" aria-label="Versi beat">
              <div className="v2-pop-head"><strong>Versi sebelumnya</strong><button className="btn ghost sm" onClick={() => setVersions(null)} aria-label="Tutup"><X size={14} /></button></div>
              {versions.length === 0 ? <p className="muted">Belum ada versi. Versi dibuat otomatis setiap kali beat disimpan ulang.</p> : (
                <ul>
                  {versions.map((v) => (
                    <li key={v.id}>
                      <span>{new Date(v.created_at).toLocaleString("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
                      <span className="muted">{v.count} beat · {fmt(v.seconds)}{v.note ? ` · ${v.note}` : ""}</span>
                      <button className="btn sm" onClick={() => void restore(v)}>Pulihkan</button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {beats.length === 0 ? (
            <div className="v2-start">
              <strong>Bagi adegan ini jadi beat</strong>
              <span className="muted">Beat adalah potongan waktu: tiap beat punya aksi, kamera, pemeran, dan dialognya sendiri. Nanti tiap beat jadi satu gambar acuan.</span>
              <div className="jr-inline">
                <button className="btn" disabled={locked} onClick={() => startEmpty(1)}>Mulai dengan 1 beat</button>
                {[2, 3, 4].map((n) => <button key={n} className="btn" disabled={locked} onClick={() => startEmpty(n)}>Bagi rata {n}</button>)}
              </div>
              {scene && <AiShots scene={scene} locked={locked} hasContent={false} onDraft={applyDraft} />}
            </div>
          ) : (<>
            <div className="v2-lane-wrap">
              <div className="v2-lane" ref={laneRef} role="group" aria-label="Jalur waktu beat">
                {beats.map((x, i) => (
                  <button key={x.key} className={`v2-block ${i === sel ? "on" : ""}`} style={{ flex: `${x.dur} 1 0` }} onClick={() => setSel(i)} aria-pressed={i === sel}
                    aria-label={`Beat ${i + 1}, ${fmt(x.dur)}`}>
                    <span className="v2-block-top"><b>{i + 1}</b><span>{fmt(x.dur)}</span></span>
                    <span className="v2-block-text clamp2">{x.action || <i className="muted">kosong</i>}</span>
                    <span className="v2-block-cast">
                      {x.cast.map((c) => <em key={c} style={{ background: tint(hue(scene, c), 0.9) }} title={scene.cast.find((m) => m.character_id === c)?.character_name} />)}
                      {x.dialogue.length > 0 && <span className="v2-say" title="Ada dialog">“”</span>}
                    </span>
                  </button>
                ))}
                {beats.slice(0, -1).map((_, i) => (
                  <span key={`h${i}`} role="separator" tabIndex={locked ? -1 : 0} aria-orientation="vertical" aria-label={`Batas beat ${i + 1} dan ${i + 2}`}
                    aria-valuenow={at[i + 1]} aria-valuemin={0} aria-valuemax={totalSec} className="v2-handle"
                    style={{ left: `${(at[i + 1] / (totalSec || 1)) * 100}%` }} onPointerDown={(e) => dragBoundary(e, i)} onKeyDown={(e) => nudgeBoundary(e, i)} />
                ))}
              </div>
              <div className="v2-ruler" aria-hidden>
                {Array.from({ length: Math.floor(totalSec) + 1 }, (_, t) => (
                  <span key={t} style={{ left: `${(t / (totalSec || 1)) * 100}%` }} className={t % (totalSec > 20 ? 5 : totalSec > 10 ? 2 : 1) === 0 ? "major" : ""}>
                    {t % (totalSec > 20 ? 5 : totalSec > 10 ? 2 : 1) === 0 ? t : ""}
                  </span>
                ))}
              </div>
            </div>

            {scene && <RevisePanel scene={scene} before={beats} locked={locked} dirty={dirty(entry)} onApply={applyRevision} />}

            <div className="v2-toolbar">
              <button className="btn sm" disabled={locked || !splitAt(beats, sel)} onClick={() => setBeats(splitAt(beats, sel))} title="Bagi beat terpilih jadi dua"><Scissors size={13} /> Bagi dua</button>
              <button className="btn sm" disabled={locked || sel >= beats.length - 1} onClick={() => setBeats(mergeNext(beats, sel))} title="Gabung dengan beat sesudahnya"><Merge size={13} /> Gabung ke berikutnya</button>
              <button className="btn sm" disabled={locked} onClick={addAtEnd}><Plus size={13} /> Beat di akhir</button>
              <select aria-label="Bagi rata" value="" disabled={locked} onChange={(e) => { if (e.target.value) redistribute(Number(e.target.value)); }}>
                <option value="">Bagi rata…</option>
                {[2, 3, 4, 5, 6, 8].map((n) => <option key={n} value={n} disabled={totalSec / n < MIN_BEAT}>{n} beat</option>)}
              </select>
              {scene && <AiShots scene={scene} locked={locked} hasContent={hasContent(beats)} onDraft={applyDraft} />}
              <span className="muted v2-total">Total {fmt(totalSec)}</span>
              {mismatch && (
                <span className="v2-mismatch">
                  <span className="warn">Durasi adegan {fmt(planned!)}</span>
                  <button className="btn sm" disabled={locked} onClick={() => setBeats(scaleTo(beats, planned!), "Durasi adegan terlalu pendek untuk jumlah beat ini")}>Samakan beat</button>
                  <button className="btn sm" disabled={locked} onClick={() => void setPlanned(totalSec)}>Samakan adegan</button>
                </span>
              )}
            </div>
            {entry.warnings.length > 0 && <ul className="v2-warns">{entry.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}

            {b && (
              <div className="v2-detail" aria-label={`Beat ${sel + 1}`}>
                <div className="v2-frame" aria-label="Gambar acuan beat">
                  {b.image_id ? <img src={api.imageUrl(b.image_id)} alt={`Gambar beat ${sel + 1}`} />
                    : <span className="muted">Belum ada gambar acuan. Pembuatan gambar per beat menyusul di langkah berikutnya.</span>}
                </div>
                <div className="v2-fields">
                  <div className="v2-fields-head">
                    <strong>Beat {sel + 1}</strong>
                    <span className="muted">{r1(at[sel])} sampai {r1(at[sel] + b.dur)} dtk</span>
                    <div className="v2-stepper" role="group" aria-label="Durasi beat">
                      <button className="btn sm" disabled={locked || beats.length < 2} aria-label="Kurangi 0,5 detik" onClick={() => setBeats(resizeWithin(beats, sel, b.dur - STEP))}>−</button>
                      <span className="mono">{fmt(b.dur)}</span>
                      <button className="btn sm" disabled={locked || beats.length < 2} aria-label="Tambah 0,5 detik" onClick={() => setBeats(resizeWithin(beats, sel, b.dur + STEP))}>+</button>
                    </div>
                    <button className="btn ghost sm danger" disabled={locked || beats.length < 2} onClick={() => remove(sel)} aria-label="Hapus beat"><Trash2 size={13} /></button>
                  </div>

                  <label className="field">Apa yang terjadi
                    <textarea rows={2} maxLength={300} value={b.action} disabled={locked} placeholder="Contoh: Momon melompat ke sofa dan menggoyangkan ekornya"
                      onChange={(e) => patchBeat(sel, { action: e.target.value })} />
                  </label>

                  <div className="field" role="group" aria-label="Ukuran dan lensa">Ukuran shot dan lensa
                    <span className="v2-presets">
                      {SIZES.map((z) => <button key={z} type="button" className={`chip preset ${b.size === z ? "on" : ""}`} aria-pressed={b.size === z} disabled={locked}
                        onClick={() => patchBeat(sel, { size: b.size === z ? "" : z })}>{z}</button>)}
                      <span className="muted">·</span>
                      {LENSES.map((l) => <button key={l} type="button" className={`chip preset ${b.lens === l ? "on" : ""}`} aria-pressed={b.lens === l} disabled={locked}
                        onClick={() => patchBeat(sel, { lens: b.lens === l ? "" : l })}>{l}mm</button>)}
                    </span>
                    {b.dur > MAX_SHOT && <span className="warn">{fmt(b.dur)}: format menganjurkan shot 1–{MAX_SHOT} dtk. Pertimbangkan “Bagi dua”.</span>}
                  </div>

                  <div className="field">Gerak kamera
                    <input value={b.camera} maxLength={120} disabled={locked} placeholder="Contoh: close-up, dolly in pelan" onChange={(e) => patchBeat(sel, { camera: e.target.value })} />
                    <span className="v2-presets">
                      {CAMERA_PRESETS.map((p) => <button key={p} type="button" className="chip preset" disabled={locked}
                        onClick={() => patchBeat(sel, { camera: b.camera ? (b.camera.toLowerCase().includes(p.toLowerCase()) ? b.camera : `${b.camera}, ${p.toLowerCase()}`) : p })}>{p}</button>)}
                    </span>
                  </div>

                  <div className="field" role="group" aria-label="Tokoh di beat ini">Siapa yang tampil
                    {scene.cast.length === 0
                      ? <span className="muted">Adegan ini belum punya pemeran. Isi di langkah Adegan. <button className="btn ghost sm" onClick={goScenes}>Ke Adegan</button></span>
                      : <span className="v2-cast">
                          {scene.cast.map((m) => {
                            const on = b.cast.includes(m.character_id);
                            return (
                              <button key={m.character_id} type="button" className={`v2-who ${on ? "on" : ""}`} aria-pressed={on} disabled={locked}
                                style={on ? { background: tint(hue(scene, m.character_id)), borderColor: tint(hue(scene, m.character_id), 0.8) } : undefined}
                                onClick={() => patchBeat(sel, { cast: on ? b.cast.filter((c) => c !== m.character_id) : [...b.cast, m.character_id],
                                  dialogue: on ? b.dialogue.filter((d) => d.character_id !== m.character_id) : b.dialogue })}>{m.character_name}</button>
                            );
                          })}
                        </span>}
                  </div>

                  <div className="field" role="group" aria-label="Dialog">Dialog
                    {b.dialogue.map((d, k) => {
                      const words = d.text.trim().split(/\s+/).filter(Boolean).length;
                      return (
                        <span className="v2-line" key={k}>
                          <select value={d.character_id} disabled={locked} aria-label="Penutur" onChange={(e) => patchBeat(sel, { dialogue: b.dialogue.map((x, n) => (n === k ? { ...x, character_id: e.target.value } : x)) })}>
                            {scene.cast.filter((m) => b.cast.includes(m.character_id) || m.character_id === d.character_id).map((m) => <option key={m.character_id} value={m.character_id}>{m.character_name}</option>)}
                          </select>
                          <input value={d.text} maxLength={300} disabled={locked} placeholder="Apa yang diucapkan" onChange={(e) => patchBeat(sel, { dialogue: b.dialogue.map((x, n) => (n === k ? { ...x, text: e.target.value } : x)) })} />
                          {words / b.dur > WORDS_PER_SECOND && <span className="chip warn" title={`${words} kata dalam ${fmt(b.dur)}`}>terlalu padat</span>}
                          <button type="button" className="btn ghost sm" disabled={locked} aria-label="Hapus dialog" onClick={() => patchBeat(sel, { dialogue: b.dialogue.filter((_, n) => n !== k) })}><X size={13} /></button>
                        </span>
                      );
                    })}
                    <button type="button" className="btn sm" disabled={locked || b.cast.length === 0} title={b.cast.length ? "" : "Pilih siapa yang tampil dulu"}
                      onClick={() => patchBeat(sel, { dialogue: [...b.dialogue, { character_id: b.cast[0], text: "" }] })}><Plus size={13} /> Tambah dialog</button>
                  </div>
                </div>
              </div>
            )}
          </>)}
        </>)}
        {scene && !entry && <p className="muted"><Loader2 size={14} className="spin" /> Memuat beat…</p>}
      </section>
    </div>
  );
}
