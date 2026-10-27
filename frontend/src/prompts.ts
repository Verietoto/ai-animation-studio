// Preset prompt (bahasa Inggris: model video/gambar umumnya lebih patuh) + riwayat prompt per perangkat.

export interface Preset { label: string; text: string }
export const PRESETS: Record<string, Preset[]> = {
  Kamera: [
    { label: "Dolly in", text: "slow dolly in" }, { label: "Dolly out", text: "slow dolly out" },
    { label: "Orbit", text: "camera slowly orbits around the subject" }, { label: "Pan kiri", text: "smooth pan left" },
    { label: "Pan kanan", text: "smooth pan right" }, { label: "Crane naik", text: "crane shot rising up" },
    { label: "Handheld", text: "handheld camera, subtle shake" }, { label: "Statis", text: "static locked-off camera" },
  ],
  Gaya: [
    { label: "Sinematik", text: "cinematic, shallow depth of field, film grain" }, { label: "Anime", text: "anime style, clean line art" },
    { label: "Claymation", text: "claymation stop-motion look" }, { label: "Film noir", text: "black and white film noir, high contrast" },
    { label: "Realistis", text: "photorealistic, natural motion" }, { label: "Cat air", text: "watercolor painting style" },
  ],
  Cahaya: [
    { label: "Golden hour", text: "warm golden hour light" }, { label: "Neon malam", text: "night scene, neon lights, wet streets" },
    { label: "Berkabut", text: "soft fog, volumetric light" }, { label: "Studio", text: "soft studio lighting" },
  ],
};

// Negative prompt (plan 13): label Indonesia, teks Inggris dikirim apa adanya.
export const NEGATIVE_PRESETS: Preset[] = [
  { label: "Teks", text: "text, subtitles" }, { label: "Watermark", text: "watermark, logo" },
  { label: "Blur", text: "blurry, low quality" }, { label: "Tangan cacat", text: "deformed hands, extra fingers" },
  { label: "Wajah berubah", text: "face morphing, identity change" },
];

// Preset untuk section Pose dan Ekspresi di Edit Foto (plan 06): teks Inggris dikirim apa adanya.
export const POSE_PRESETS: Preset[] = [
  { label: "Berdiri santai", text: "standing relaxed, weight on one leg" }, { label: "Tangan di pinggang", text: "hands on hips, weight on one leg" },
  { label: "Duduk", text: "sitting on a stool, hands on knees" }, { label: "Berlari", text: "running mid-stride, dynamic" },
  { label: "Melambai", text: "waving with one hand raised" }, { label: "Menunjuk", text: "pointing forward with one arm" },
  { label: "Tangan bersilang", text: "arms crossed over the chest" },
];
export const EXPRESSION_PRESETS: Preset[] = [
  { label: "Netral", text: "calm neutral expression" }, { label: "Senyum", text: "gentle warm smile" },
  { label: "Tertawa", text: "big open smile, laughing" }, { label: "Sedih", text: "sad, downcast eyes" },
  { label: "Marah", text: "angry, furrowed brows" }, { label: "Terkejut", text: "surprised, eyes wide, mouth slightly open" },
  { label: "Mengedip", text: "playful wink" },
];

/** Tambahkan frasa ke prompt (dipisah koma); frasa yang sudah ada tidak digandakan. */
export function addPhrase(prompt: string, phrase: string): string {
  if (prompt.toLowerCase().includes(phrase.toLowerCase())) return prompt;
  const base = prompt.trimEnd().replace(/[,.]$/, "");
  return base ? `${base}, ${phrase}` : phrase;
}

const KEY = "ai-studio:prompt-history";
const MAX = 20;

export function loadHistory(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "[]") as unknown;
    return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === "string").slice(0, MAX) : [];
  } catch { return []; }   // storage diblokir/rusak: riwayat kosong, aplikasi tetap jalan
}

export function pushHistory(prompt: string): void {
  const p = prompt.trim();
  if (!p) return;
  try { localStorage.setItem(KEY, JSON.stringify([p, ...loadHistory().filter((x) => x !== p)].slice(0, MAX))); } catch { /* abaikan */ }
}
