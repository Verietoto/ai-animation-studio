import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Clapperboard, Loader2, MapPin, Plus, SlidersHorizontal, Trash2, UserRound } from "lucide-react";
import { toast } from "sonner";
import { api, Character, Clip, Film, FilmDetail, Img, JourneyState, SceneUpdate } from "../api";
import { useAsync } from "../components";
import { EmptyState, Stage } from "../ui";
import { SaveText } from "../storyboard/fields";
import { SceneInspector } from "../storyboard/Inspector";
import { LocationsView } from "../storyboard/Locations";
import { Board, ScriptView, TimelineView } from "../storyboard/Views";
import { hint, initialStep, Stepper } from "../storyboard/journey/Stepper";
import { StepCast } from "../storyboard/journey/StepCast";
import { StepScript } from "../storyboard/journey/StepScript";
import { StepTimeline } from "../storyboard/journey/StepTimeline";
import { StepPrevis } from "../storyboard/journey/StepPrevis";
import { StepProduce } from "../storyboard/journey/StepProduce";
import { initialV2Step, V2Flow } from "../storyboard/v2/V2Flow";

type View = "board" | "script" | "timeline" | "locations";
const VIEWS: [View, string][] = [["board", "Papan"], ["script", "Naskah"], ["timeline", "Timeline"], ["locations", "Latar"]];
const ASPECTS = ["16:9", "9:16", "1:1", "4:3", "21:9"];
const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
const isTyping = (el: EventTarget | null) =>
  el instanceof HTMLElement && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));

export default function Storyboard({ clips, images, characters, addImage, focusFilm, onGenerated, reloadCharacters }: {
  clips: Clip[]; images: Img[]; characters: Character[]; addImage: (i: Img) => void; focusFilm?: string | null;
  reloadCharacters: () => void;   // karakter baru dibuat dari langkah 1: muat ulang daftar di App
  /** Dipanggil setelah keyframe/video/gambar latar dibuat: App memuat ulang gambar, klip, dan biaya hari ini. */
  onGenerated: () => void;
}) {
  const [films, setFilms] = useState<Film[]>([]);
  const [activeId, setActiveId] = useState<string | null>(focusFilm ?? null);
  const activeIdRef = useRef<string | null>(null);
  activeIdRef.current = activeId;
  const [detail, setDetail] = useState<FilmDetail | null>(null);
  const [journey, setJourney] = useState<JourneyState | null>(null);   // keadaan alur episode (plan 15)
  const [step, setStep] = useState(1);
  const [advanced, setAdvanced] = useState(false);   // Mode lanjutan: tab lama (Papan/Naskah/Timeline/Latar)
  const stepFor = useRef<string | null>(null);
  const [flow, setFlow] = useState<"v2" | "classic">(() => { try { return localStorage.getItem("sb-flow") === "classic" ? "classic" : "v2"; } catch { return "v2"; } });
  const [v2step, setV2step] = useState(1);   // langkah Storyboard v2 (plan 18)
  const v2For = useRef<string | null>(null);
  const [view, setView] = useState<View>("board");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [pending, setPending] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const locs = useAsync(api.locations, []);
  const locations = locs.data ?? [];
  const reloadLocs = useCallback(() => { void api.locations().then(locs.setData).catch((e: Error) => toast.error(e.message)); }, [locs.setData]);
  const seq = useRef<Record<string, number>>({});

  const loadFilms = useCallback(() => api.films().then(setFilms).catch((e: Error) => setError(e.message)), []);
  const loadDetail = useCallback((id: string) => Promise.all([api.film(id).then(setDetail), api.journey(id).then(setJourney)])
    .catch((e: Error) => setError(e.message)), []);
  const goStep = useCallback((n: number) => {
    setStep(n);
    try { if (activeIdRef.current) localStorage.setItem(`sb-step:${activeIdRef.current}`, String(n)); } catch { /* penyimpanan tidak tersedia */ }
  }, []);

  const changeFlow = (f: "v2" | "classic") => {
    setFlow(f); if (f === "v2") { setAdvanced(false); setView("board"); }
    try { localStorage.setItem("sb-flow", f); } catch { /* penyimpanan tidak tersedia */ }
  };
  const goV2 = useCallback((n: number) => {
    setV2step(n);
    try { if (activeIdRef.current) localStorage.setItem(`sb2-step:${activeIdRef.current}`, String(n)); } catch { /* abaikan */ }
  }, []);

  useEffect(() => { void loadFilms(); }, [loadFilms]);
  useEffect(() => { if (focusFilm) setActiveId(focusFilm); }, [focusFilm]);
  useEffect(() => { if (!activeId && films.length) setActiveId(films[0].id); }, [films, activeId]);
  useEffect(() => {   // langkah awal v2: yang tersimpan, atau titik terjauh yang sudah punya isi
    if (!journey || !activeId || journey.film_id !== activeId || v2For.current === activeId) return;
    v2For.current = activeId;
    let saved = 0;
    try { saved = Number(localStorage.getItem(`sb2-step:${activeId}`)); } catch { /* abaikan */ }
    setV2step(saved >= 1 && saved <= 6 ? saved : initialV2Step(journey));
  }, [journey, activeId]);
  useEffect(() => { setDetail(null); setJourney(null); stepFor.current = null; v2For.current = null; setConfirmDelete(false); setSelectedId(null); if (activeId) void loadDetail(activeId); }, [activeId, loadDetail]);
  useEffect(() => {   // langkah awal: yang tersimpan, atau diturunkan dari isi episode (episode lama dengan hasil langsung ke Animasi)
    if (!journey || !activeId || journey.film_id !== activeId || stepFor.current === activeId) return;
    stepFor.current = activeId;
    let saved = 0;
    try { saved = Number(localStorage.getItem(`sb-step:${activeId}`)); } catch { /* abaikan */ }
    setStep(saved >= 1 && saved <= 5 ? saved : initialStep(journey));
  }, [journey, activeId]);

  const scenes = detail?.scenes ?? [];
  const rendering = detail?.render_status === "rendering";
  const busy = rendering || scenes.some((s) => s.status === "video_diproses");
  const selected = scenes.find((s) => s.id === selectedId) ?? scenes[0] ?? null;
  useEffect(() => {   // polling hanya selama ada render atau video yang berjalan
    if (!busy || !activeId) return;
    const t = setInterval(() => { void loadDetail(activeId); void loadFilms(); }, 3000);
    return () => clearInterval(t);
  }, [busy, activeId, loadDetail, loadFilms]);

  /** Simpan sebagian field adegan. Hanya respons terbaru per adegan yang dipakai; gagal = toast dan galat dilempar ulang (teks tidak hilang). */
  const patch = useCallback(async (id: string, body: SceneUpdate) => {
    const n = (seq.current[id] = (seq.current[id] ?? 0) + 1);
    setPending((p) => p + 1);
    try {
      const s = await api.updateScene(id, body);
      if (seq.current[id] === n) setDetail((d) => (d ? { ...d, scenes: d.scenes.map((x) => (x.id === id ? s : x)) } : d));
      if ("clip_id" in body) { void loadFilms(); if (activeId) void loadDetail(activeId); }   // kemajuan episode, durasi, dan peringatan
      return s;
    } catch (e) { toast.error((e as Error).message); throw e; } finally { setPending((p) => p - 1); }
  }, [activeId, loadDetail, loadFilms]);

  const run = useCallback(async (fn: () => Promise<unknown>) => {
    try { await fn(); } catch (e) { toast.error((e as Error).message); if (activeId) void loadDetail(activeId); }
  }, [activeId, loadDetail]);

  const addScene = useCallback((after?: string) => run(async () => {
    const s = await api.addScene(activeId!, { after_scene_id: after });
    await loadDetail(activeId!); await loadFilms();
    setSelectedId(s.id); setFocusId(s.id);
  }), [activeId, run, loadDetail, loadFilms]);
  const duplicate = useCallback((id: string) => run(async () => {
    const s = await api.duplicateScene(id);
    await loadDetail(activeId!); await loadFilms(); setSelectedId(s.id);
  }), [activeId, run, loadDetail, loadFilms]);
  const remove = (id: string) => run(async () => {
    const at = scenes.findIndex((s) => s.id === id);
    await api.deleteScene(id);
    setSelectedId(scenes[at + 1]?.id ?? scenes[at - 1]?.id ?? null);
    await loadDetail(activeId!); await loadFilms();
  });
  const bulkRemove = async (ids: string[]) => {   // satu permintaan atomik; galat dilempar ulang agar pilihan di papan dipertahankan
    try {
      await api.bulkDeleteScenes(activeId!, ids);
      setSelectedId((cur) => (cur && ids.includes(cur) ? null : cur));
      await loadDetail(activeId!); await loadFilms();
      toast.success(`${ids.length} adegan dihapus`);
    } catch (e) { toast.error((e as Error).message); if (activeId) void loadDetail(activeId); throw e; }
  };
  const reorder = (ids: string[]) => run(async () => {
    setDetail((d) => d && { ...d, scenes: ids.map((id, i) => ({ ...d.scenes.find((s) => s.id === id)!, position: i, number: i + 1 })) });   // optimistis
    await api.reorderScenes(activeId!, ids);
    await loadDetail(activeId!); await loadFilms();
  });
  const saveFilm = (body: Parameters<typeof api.updateFilm>[1]) => api.updateFilm(activeId!, body)
    .then(() => Promise.all([loadDetail(activeId!), loadFilms()]))
    .catch((e: Error) => { toast.error(e.message); throw e; });
  const createFilm = () => run(async () => {
    const f = await api.createFilm(newTitle.trim()); setNewTitle(""); await loadFilms(); setActiveId(f.id); setView("board");
  });
  const deleteFilm = () => run(async () => {
    await api.deleteFilm(activeId!); setActiveId(null); setDetail(null); await loadFilms();
  });

  const sceneStep = advanced || (flow === "v2" ? v2step === 4 : step >= 3);   // langkah yang menampilkan daftar adegan
  useEffect(() => {   // N = adegan baru setelah yang dipilih, D = duplikat, panah = pindah adegan (di luar kolom teks)
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target) || !detail || view === "locations" || !sceneStep) return;
      const at = scenes.findIndex((s) => s.id === selected?.id);
      if (e.key.toLowerCase() === "n" && !rendering) { e.preventDefault(); void addScene(selected?.id); }
      else if (e.key.toLowerCase() === "d" && selected && !rendering) { e.preventDefault(); void duplicate(selected.id); }
      else if (e.key === "ArrowDown" || e.key === "ArrowRight") { if (scenes[at + 1]) { e.preventDefault(); setSelectedId(scenes[at + 1].id); } }
      else if (e.key === "ArrowUp" || e.key === "ArrowLeft") { if (at > 0) { e.preventDefault(); setSelectedId(scenes[at - 1].id); } }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [detail, view, scenes, selected, rendering, addScene, duplicate, sceneStep]);

  const madeSeconds = scenes.reduce((sum, s) => sum + (s.clip_id ? detail?.durations[s.clip_id] ?? 0 : 0), 0);
  const readyClips = useMemo(() => clips.filter((c) => c.status === "completed" && c.has_file), [clips]);

  const afterGenerate = () => { onGenerated(); if (activeId) { void loadDetail(activeId); void loadFilms(); } };

  const main = (
    <div className="sb-main">
      {(advanced || view === "locations") && (
        <div className="seg" role="tablist" aria-label="Tampilan storyboard">
          {VIEWS.map(([id, label]) => <button key={id} role="tab" aria-selected={view === id} className={view === id ? "on" : ""} onClick={() => setView(id)}>{label}</button>)}
        </div>
      )}

      {view === "locations" && !advanced && <button className="btn ghost sm" onClick={() => setView("board")}><ArrowLeft size={14} /> Kembali ke alur episode</button>}
      {view === "locations" && <LocationsView locations={locations} images={images} addImage={addImage} reload={reloadLocs} onGenerated={onGenerated} />}

      {view !== "locations" && !activeId && <EmptyState icon={<Clapperboard size={36} />} title="Buat episode pertamamu"
        hint="Beri judul di kiri, lalu tulis adegannya: latar, pemeran, tampilan, dan apa yang mereka lakukan." />}
      {view !== "locations" && activeId && !detail && <p className="muted"><Loader2 size={14} className="spin" /> Memuat…</p>}

      {view !== "locations" && detail && (<>
        <div className="sb-head">
          <label className="ep-no">Ep
            <SaveText label="Nomor episode" value={String(detail.number)} maxLength={4} className="ep-no-input"
              onSave={(v) => { const n = Number(v); if (!Number.isInteger(n) || n < 1) { toast.error("Nomor episode 1 sampai 9999"); return Promise.reject(new Error("nomor")); } return saveFilm({ number: n }); }} />
          </label>
          <SaveText label="Judul episode" className="sb-title" value={detail.title} maxLength={120} onSave={(v) => saveFilm({ title: v })} />
          <span className="chip"><b>{detail.ready_count}/{detail.scene_count}</b> adegan siap</span>
          {detail.planned_seconds > 0 && <span className="chip" title="Total durasi rencana vs total video yang sudah ada">rencana <b>{fmtTime(detail.planned_seconds)}</b> · jadi <b>{fmtTime(madeSeconds)}</b></span>}
          <div className="seg" role="group" aria-label="Pilih alur kerja">
            <button aria-pressed={flow === "v2"} className={flow === "v2" ? "on" : ""} onClick={() => changeFlow("v2")}>Storyboard v2</button>
            <button aria-pressed={flow === "classic"} className={flow === "classic" ? "on" : ""} onClick={() => changeFlow("classic")}>Alur lama</button>
          </div>
          {flow === "v2"
            ? <span className="chip" title="Rasio diatur di pengaturan proyek (langkah Proyek & pemeran)">rasio <b>{detail.aspect_ratio}</b></span>
            : <select aria-label="Rasio aspek episode" value={detail.aspect_ratio} disabled={rendering} onChange={(e) => void saveFilm({ aspect_ratio: e.target.value }).catch(() => {})}>
                {[...new Set([...ASPECTS, detail.aspect_ratio])].map((a) => <option key={a} value={a}>{a}</option>)}
              </select>}
          <span className="muted save-state" aria-live="polite">{pending > 0 ? "Menyimpan…" : "Tersimpan"}</span>
          {flow === "classic" && <button className="btn ghost sm" onClick={() => setAdvanced((a) => !a)}
            title="Tab lama: Papan, Naskah per adegan, Timeline, Latar"><SlidersHorizontal size={14} /> {advanced ? "Kembali ke alur" : "Mode lanjutan"}</button>}
          {confirmDelete
            ? <><button className="btn danger sm" disabled={rendering} onClick={() => void deleteFilm()}>Ya, hapus episode</button><button className="btn ghost sm" onClick={() => setConfirmDelete(false)}>Batal</button></>
            : <button className="btn ghost sm danger" disabled={rendering} onClick={() => setConfirmDelete(true)}><Trash2 size={14} /> Hapus</button>}
        </div>
        {advanced && <details className="synopsis">
          <summary>Sinopsis{detail.synopsis ? "" : " (kosong)"}</summary>
          <SaveText label="Sinopsis" multiline rows={3} value={detail.synopsis} maxLength={2000} placeholder="Ringkasan cerita episode ini"
            onSave={(v) => saveFilm({ synopsis: v })} />
        </details>}
        {error && <p className="error">{error}</p>}

        {!advanced && !journey && <p className="muted"><Loader2 size={14} className="spin" /> Memuat alur…</p>}
        {!advanced && journey && flow === "v2" && (
          <V2Flow detail={detail} journey={journey} step={v2step} onStep={goV2} locked={rendering} characters={characters} locations={locations} images={images}
            selectedId={selected?.id ?? null} addImage={addImage} reload={() => loadDetail(detail.id)} reloadAll={() => Promise.all([loadDetail(detail.id), loadFilms()])}
            reloadLocations={reloadLocs} reloadCharacters={reloadCharacters} onGenerated={afterGenerate} onManageLocations={() => setView("locations")}
            saveSynopsis={(v) => saveFilm({ synopsis: v })} onSelect={setSelectedId} onAdd={() => void addScene()} onDelete={(id) => void remove(id)}
            onBulkDelete={bulkRemove} onReorder={(ids) => void reorder(ids)}
            onRender={() => void run(async () => { await api.renderFilm(detail.id); await loadDetail(detail.id); })} />
        )}
        {!advanced && journey && flow === "classic" && (<>
          <Stepper step={step} onStep={goStep} journey={journey} />
          {step === 1 && <StepCast filmId={detail.id} journey={journey} characters={characters} locations={locations} images={images} locked={rendering}
            addImage={addImage} reload={() => loadDetail(detail.id)} reloadLocations={reloadLocs} reloadCharacters={reloadCharacters}
            onGenerated={afterGenerate} onManageLocations={() => setView("locations")} />}
          {step === 2 && <StepScript filmId={detail.id} synopsis={detail.synopsis} journey={journey} characters={characters} locations={locations}
            locked={rendering} reload={() => loadDetail(detail.id)} saveSynopsis={(v) => saveFilm({ synopsis: v })} />}
          {step === 3 && <StepTimeline detail={detail} journey={journey} selectedId={selected?.id ?? null} locked={rendering}
            reload={() => Promise.all([loadDetail(detail.id), loadFilms()])} onSelect={setSelectedId} onAdd={() => void addScene()}
            onDelete={(id) => void remove(id)} onBulkDelete={bulkRemove} onReorder={(ids) => void reorder(ids)} goScript={() => goStep(2)} />}
          {step === 4 && <StepPrevis detail={detail} journey={journey} locked={rendering} reload={() => loadDetail(detail.id)} onGenerated={afterGenerate} />}
          {step === 5 && <StepProduce detail={detail} journey={journey} locked={rendering} reload={() => Promise.all([loadDetail(detail.id), loadFilms()])}
            onGenerated={afterGenerate} onSelect={setSelectedId}
            onRender={() => void run(async () => { await api.renderFilm(detail.id); await loadDetail(detail.id); })} />}
          <div className="jr-foot">
            <span className="muted">{hint(step, journey) ?? "Siap untuk langkah berikutnya."}</span>
            <button className="btn" disabled={step <= 1} onClick={() => goStep(step - 1)}><ArrowLeft size={14} /> Kembali</button>
            <button className="btn primary" disabled={step >= 5} onClick={() => goStep(step + 1)}>Lanjut <ArrowRight size={14} /></button>
          </div>
        </>)}

        {advanced && view === "board" && (scenes.length === 0
          ? <EmptyState icon={<Clapperboard size={36} />} title="Episode ini belum punya adegan" hint="Tambah adegan, lalu isi latar, pemeran, dan aksinya.">
              <button className="btn primary" onClick={() => void addScene()}><Plus size={14} /> Adegan pertama</button>
            </EmptyState>
          : <Board scenes={scenes} selectedId={selected?.id ?? null} locked={rendering} onSelect={setSelectedId} onReorder={(ids) => void reorder(ids)} onAdd={() => void addScene()} onDelete={(id) => void remove(id)} onBulkDelete={bulkRemove} />)}
        {advanced && view === "script" && <ScriptView scenes={scenes} selectedId={selected?.id ?? null} focusId={focusId} locked={rendering}
          locations={locations} characters={characters} onSelect={setSelectedId} onPatch={patch} onAdd={(after) => void addScene(after)} onDelete={(id) => void remove(id)} />}
        {advanced && view === "timeline" && <TimelineView detail={detail} rendering={rendering}
          onRender={() => void run(async () => { await api.renderFilm(detail.id); await loadDetail(detail.id); })} />}
      </>)}
    </div>
  );

  const inspector = view !== "locations" && detail && selected && sceneStep
    ? <SceneInspector key={selected.id} scene={selected} aspect={detail.aspect_ratio} locked={rendering} locations={locations} characters={characters} images={images} clips={readyClips}
        onPatch={(body) => patch(selected.id, body)} onDelete={() => void remove(selected.id)} onDuplicate={() => void duplicate(selected.id)}
        onNewLocation={async (name) => { const l = await api.createLocation({ name }); reloadLocs(); return l; }}
        onGenerated={() => { onGenerated(); void loadDetail(selected.film_id); void loadFilms(); }}
        onManageLocations={() => setView("locations")} promptMode={flow === "v2" && !advanced} />
    : <p className="muted">{view === "locations" ? "Latar dipakai ulang di banyak adegan." : !sceneStep && !advanced ? `Ikuti langkah di tengah; detail adegan muncul di sini mulai langkah ${flow === "v2" ? "Adegan" : "Timeline"}.` : "Pilih atau tambah adegan untuk mengisi detailnya."}</p>;

  return (
    <div className="sb">
      <aside className="sb-list" aria-label="Daftar episode">
        <form onSubmit={(e) => { e.preventDefault(); if (newTitle.trim()) void createFilm(); }} className="sb-new">
          <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="Judul episode baru" maxLength={120} aria-label="Judul episode baru" />
          <button className="btn primary sm" disabled={!newTitle.trim()} aria-label="Buat episode"><Plus size={14} /></button>
        </form>
        <ul>
          {films.map((f) => (
            <li key={f.id}>
              <button className={`film-item ${f.id === activeId && view !== "locations" ? "on" : ""}`} onClick={() => { setActiveId(f.id); if (view === "locations") setView("board"); }}>
                <strong className="clamp1">Ep {f.number} · {f.title}</strong>
                <span className="muted">{f.ready_count}/{f.scene_count} adegan siap{f.planned_seconds ? ` · rencana ${fmtTime(f.planned_seconds)}` : ""}{f.render_status === "rendering" ? " · render…" : f.has_file ? (f.stale ? " · render ulang" : " · dirender") : ""}</span>
              </button>
            </li>
          ))}
        </ul>
        {films.length === 0 && <p className="muted">Belum ada episode.</p>}
        <p className="muted bible-title">Bahan cerita</p>
        <button className={`film-item ${view === "locations" ? "on" : ""}`} onClick={() => setView("locations")}>
          <strong><MapPin size={13} /> Latar</strong><span className="muted">{locations.length} latar</span>
        </button>
        <button className="film-item" onClick={() => { window.location.hash = "#/characters"; }}>
          <strong><UserRound size={13} /> Karakter & tampilan</strong><span className="muted">{characters.length} karakter</span>
        </button>
      </aside>
      <Stage canvas={main} inspector={inspector} />
    </div>
  );
}
