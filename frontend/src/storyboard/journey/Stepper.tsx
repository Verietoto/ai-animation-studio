// Penanda langkah alur episode (plan 15). Tidak mengunci: semua langkah bisa dibuka kapan saja; tanda hanya menunjukkan kemajuan.
import { Check } from "lucide-react";
import { JourneyState } from "../../api";

export const STEPS = [
  { id: 1, label: "Pemeran & latar" },
  { id: 2, label: "Naskah" },
  { id: 3, label: "Timeline" },
  { id: 4, label: "Previs 3D", optional: true },
  { id: 5, label: "Animasi" },
] as const;

/** Apakah langkah dianggap selesai menurut data episode (diturunkan, tidak disimpan). */
export function isDone(step: number, j: JourneyState): boolean {
  const p = j.progress;
  switch (step) {
    case 1: return j.characters.length > 0 && j.locations.length > 0;
    case 2: return j.script.trim().length > 0;
    case 3: return p.scenes > 0;
    case 4: return j.previs_skipped || p.previs > 0 || p.blockout > 0;
    default: return p.scenes > 0 && p.video_ready >= p.scenes;
  }
}

/** Langkah awal saat episode dibuka: episode lama dengan hasil langsung ke Animasi, bukan mengulang dari awal. */
export function initialStep(j: JourneyState): number {
  const p = j.progress;
  if (p.scenes > 0 && (p.keyframe > 0 || p.video > 0)) return 5;
  if (p.scenes > 0 || j.script.trim()) return 3;
  if (j.characters.length > 0 || j.locations.length > 0) return 2;
  return 1;
}

/** Kalimat singkat tentang apa yang masih kurang di langkah ini (tidak memblokir tombol Lanjut). */
export function hint(step: number, j: JourneyState): string | null {
  const p = j.progress;
  switch (step) {
    case 1: return j.characters.length === 0 ? "Belum ada karakter dipilih." : j.locations.length === 0 ? "Belum ada latar dipilih." : null;
    case 2: return j.script.trim() ? (j.mentions.unknown.length ? `${j.mentions.unknown.length} mention belum ada di episode.` : null) : "Naskah masih kosong (boleh dilewati, adegan bisa dibuat manual).";
    case 3: return p.scenes === 0 ? "Belum ada adegan." : p.no_location > 0 ? `${p.no_location} adegan belum punya latar.` : null;
    case 4: return "Opsional: boleh langsung lanjut ke animasi.";
    default: return null;
  }
}

export function Stepper({ step, onStep, journey }: { step: number; onStep: (n: number) => void; journey: JourneyState }) {
  return (
    <nav className="jr-steps" aria-label="Langkah pembuatan episode">
      {STEPS.map((s) => {
        const done = isDone(s.id, journey);
        const warn = (s.id === 3 && journey.script_changed) || (s.id === 2 && journey.mentions.unknown.length > 0);
        return (
          <button key={s.id} className={`jr-step ${step === s.id ? "on" : ""} ${done ? "done" : ""}`} aria-current={step === s.id ? "step" : undefined}
            onClick={() => onStep(s.id)}>
            <span className="jr-num">{done ? <Check size={12} /> : s.id}</span>
            <span className="jr-label">{s.label}</span>
            {"optional" in s && <span className="chip meta">opsional</span>}
            {warn && <span className="jr-warn" title={s.id === 3 ? "Naskah berubah sejak adegan dibuat" : "Ada mention yang belum ada di episode"}>!</span>}
          </button>
        );
      })}
    </nav>
  );
}
