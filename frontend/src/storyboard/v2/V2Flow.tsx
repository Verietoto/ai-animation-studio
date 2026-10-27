// Alur Storyboard v2 (plan 18): enam langkah per episode. Pengaturan proyek berlaku untuk semua episode; langkah lain per episode.
// Langkah pemeran, naskah, dan adegan memakai ulang komponen alur lama (plan 15).
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Check, CircleAlert, ImageOff } from "lucide-react";
import { api, Character, FilmDetail, Img, JourneyState, Location } from "../../api";
import { StepCast } from "../journey/StepCast";
import { StepScript } from "../journey/StepScript";
import { StepTimeline } from "../journey/StepTimeline";
import { hint as classicHint, isDone as classicDone } from "../journey/Stepper";
import { BeatEditor } from "./BeatEditor";
import { ProjectSettingsPanel, ProjectSummary, useProjectSettings } from "./ProjectSettings";
import { StepVideo } from "./StepVideo";
import { StepVoices } from "./StepVoices";

export const V2_STEPS = [
  { id: 1, label: "Proyek & pemeran", classic: 1 },
  { id: 2, label: "Suara", optional: true },
  { id: 3, label: "Naskah", classic: 2 },
  { id: 4, label: "Adegan", classic: 3 },
  { id: 5, label: "Beat" },
  { id: 6, label: "Gambar & video" },
] as const;

/** Langkah awal saat episode dibuka: lanjut dari titik terjauh yang sudah punya isi. */
export function initialV2Step(j: JourneyState): number {
  if (j.progress.scenes > 0) return 5;
  if (j.script.trim()) return 4;
  if (j.characters.length > 0 || j.locations.length > 0) return 3;
  return 1;
}

function v2Done(step: number, j: JourneyState): boolean {
  const s = V2_STEPS.find((x) => x.id === step);
  return !!s && "classic" in s ? classicDone(s.classic, j) : false;
}
function v2Hint(step: number, j: JourneyState): string | null {
  const s = V2_STEPS.find((x) => x.id === step);
  if (s && "classic" in s) return classicHint(s.classic, j);
  if (step === 2) return "Opsional: boleh dilewati.";
  if (step === 5 && j.progress.scenes === 0) return "Belum ada adegan; buat dulu di langkah Adegan.";
  return null;
}

interface Props {
  detail: FilmDetail; journey: JourneyState; step: number; onStep: (n: number) => void; locked: boolean;
  characters: Character[]; locations: Location[]; images: Img[]; selectedId: string | null;
  addImage: (i: Img) => void; reload: () => Promise<unknown>; reloadAll: () => Promise<unknown>; reloadLocations: () => void; reloadCharacters: () => void;
  onGenerated: () => void; onManageLocations: () => void; saveSynopsis: (v: string) => Promise<unknown>;
  onSelect: (id: string) => void; onAdd: () => void; onDelete: (id: string) => void; onBulkDelete: (ids: string[]) => Promise<unknown>; onReorder: (ids: string[]) => void;
  onRender: () => void;
}

function Checklist({ detail, journey, goStep }: { detail: FilmDetail; journey: JourneyState; goStep: (n: number) => void }) {
  const [beatScenes, setBeatScenes] = useState<number | null>(null);
  const [beatSeconds, setBeatSeconds] = useState(0);
  const ids = detail.scenes.map((s) => s.id).join(",");
  useEffect(() => {
    let alive = true;
    void Promise.all(detail.scenes.map((s) => api.beats(s.id).catch(() => null))).then((all) => {
      if (!alive) return;
      const withBeats = all.filter((r) => r && r.beats.length > 0);
      setBeatScenes(withBeats.length);
      setBeatSeconds(withBeats.reduce((sum, r) => sum + (r!.beats[r!.beats.length - 1]?.end ?? 0), 0));
    });
    return () => { alive = false; };
  }, [ids]);   // eslint-disable-line react-hooks/exhaustive-deps

  const noSheet = journey.characters.filter((c) => !c.has_sheet);
  const noLocImg = journey.locations.filter((l) => !l.image_id);
  const rows: { ok: boolean; text: string; go?: number }[] = [
    { ok: journey.characters.length > 0, text: journey.characters.length ? `${journey.characters.length} karakter di episode ini` : "Belum ada karakter", go: 1 },
    { ok: noSheet.length === 0 && journey.characters.length > 0, text: noSheet.length ? `${noSheet.map((c) => c.name).join(", ")} belum punya lembar tampilan (gambar acuan kurang konsisten)` : "Semua karakter punya lembar tampilan", go: 1 },
    { ok: journey.locations.length > 0 && noLocImg.length === 0, text: noLocImg.length ? `Latar tanpa gambar: ${noLocImg.map((l) => l.name).join(", ")}` : journey.locations.length ? "Semua latar punya gambar" : "Belum ada latar", go: 1 },
    { ok: detail.scene_count > 0, text: detail.scene_count ? `${detail.scene_count} adegan` : "Belum ada adegan", go: 4 },
    { ok: beatScenes != null && beatScenes === detail.scene_count && detail.scene_count > 0,
      text: beatScenes == null ? "Memeriksa beat…" : `${beatScenes} dari ${detail.scene_count} adegan sudah dibagi beat (${Math.round(beatSeconds)} dtk)`, go: 5 },
  ];
  return (
    <ul className="v2-check" aria-label="Kesiapan episode">
      {rows.map((r) => (
        <li key={r.text} className={r.ok ? "ok" : "todo"}>
          {r.ok ? <Check size={14} /> : <CircleAlert size={14} />}<span>{r.text}</span>
          {!r.ok && r.go && <button className="btn ghost sm" onClick={() => goStep(r.go!)}>Perbaiki</button>}
        </li>
      ))}
    </ul>
  );
}

export function V2Flow(p: Props) {
  const { s: settings, setS, reload: reloadSettings, error } = useProjectSettings();
  const { detail, journey, step, onStep, locked } = p;
  const meta = V2_STEPS.find((x) => x.id === step)!;

  return (
    <>
      <div className="v2-bar">
        <nav className="jr-steps" aria-label="Langkah Storyboard v2">
          {V2_STEPS.map((s) => {
            const done = v2Done(s.id, journey);
            const warn = (s.id === 4 && journey.script_changed) || (s.id === 3 && journey.mentions.unknown.length > 0);
            return (
              <button key={s.id} className={`jr-step ${step === s.id ? "on" : ""} ${done ? "done" : ""}`} aria-current={step === s.id ? "step" : undefined} onClick={() => onStep(s.id)}>
                <span className="jr-num">{done ? <Check size={12} /> : s.id}</span>
                <span className="jr-label">{s.label}</span>
                {"optional" in s && <span className="chip meta">opsional</span>}
                {warn && <span className="jr-warn" title={s.id === 4 ? "Naskah berubah sejak adegan dibuat" : "Ada mention yang belum ada di episode"}>!</span>}
              </button>
            );
          })}
        </nav>
        {settings && <ProjectSummary s={settings} onOpen={() => onStep(1)} />}
      </div>
      {error && <p className="error">Pengaturan proyek gagal dimuat: {error}</p>}

      {step === 1 && (
        <div className="v2-step1">
          {settings && <ProjectSettingsPanel s={settings} setS={setS} onChanged={() => { void reloadSettings(); void p.reloadAll(); }} />}
          <StepCast filmId={detail.id} journey={journey} characters={p.characters} locations={p.locations} images={p.images} locked={locked}
            addImage={p.addImage} reload={p.reload} reloadLocations={p.reloadLocations} reloadCharacters={p.reloadCharacters}
            onGenerated={p.onGenerated} onManageLocations={p.onManageLocations} />
        </div>
      )}
      {step === 2 && <StepVoices characters={journey.characters} locked={locked} onChanged={() => {}} goCast={() => onStep(1)} />}
      {step === 3 && <StepScript filmId={detail.id} synopsis={detail.synopsis} journey={journey} characters={p.characters} locations={p.locations}
        locked={locked} reload={p.reload} saveSynopsis={p.saveSynopsis} />}
      {step === 4 && <StepTimeline detail={detail} journey={journey} selectedId={p.selectedId} locked={locked} reload={p.reloadAll}
        onSelect={p.onSelect} onAdd={p.onAdd} onDelete={p.onDelete} onBulkDelete={p.onBulkDelete} onReorder={p.onReorder} goScript={() => onStep(3)} />}
      {step === 5 && <BeatEditor detail={detail} locked={locked} onChanged={() => { void p.reload(); }} goScenes={() => onStep(4)} />}
      {step === 6 && (<>
        <StepVideo detail={detail} settings={settings} characters={p.characters} locations={p.locations} locked={locked} reload={p.reload} onGenerated={p.onGenerated} onRender={p.onRender} goStep={onStep} />
        <details className="jr-card v2-ready">
          <summary><ImageOff size={14} /> Kesiapan bahan episode</summary>
          <Checklist detail={detail} journey={journey} goStep={onStep} />
          <p className="muted">Video dibuat dari prompt adegan; gambar karakter dan latar yang disebut di prompt dikirim sebagai referensi.</p>
        </details>
      </>)}

      <div className="jr-foot">
        <span className="muted">{v2Hint(step, journey) ?? (meta.id === 6 ? "" : "Siap untuk langkah berikutnya.")}</span>
        <button className="btn" disabled={step <= 1} onClick={() => onStep(step - 1)}><ArrowLeft size={14} /> Kembali</button>
        <button className="btn primary" disabled={step >= V2_STEPS.length} onClick={() => onStep(step + 1)}>Lanjut <ArrowRight size={14} /></button>
      </div>
    </>
  );
}
