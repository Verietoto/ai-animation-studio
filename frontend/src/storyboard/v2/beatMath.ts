// Logika murni jalur waktu beat (plan 18). Beat disunting sebagai DAFTAR DURASI: awal/akhir diturunkan dari jumlah kumulatif,
// jadi susunan selalu bersambung tanpa celah atau tumpang tindih (aturan server di backend/app/beats.py), tidak mungkin salah.
import type { Beat, BeatDialogue } from "../../api";

export const MIN_BEAT = 1;      // detik; sama dengan server
export const STEP = 0.5;        // pembulatan seret/tombol
export const r1 = (n: number) => Math.round(n * 10) / 10;

export interface BeatDraft {
  key: string;                  // kunci React stabil; tidak dikirim ke server
  id?: string;                  // id server; kosong untuk beat baru
  dur: number;
  action: string; camera: string; size: string; lens: string; cast: string[]; dialogue: BeatDialogue[];
  image_id: string | null;
}

let counter = 0;
export const newKey = () => `b${Date.now().toString(36)}${(counter++).toString(36)}`;

export const blank = (dur: number): BeatDraft => ({ key: newKey(), dur: r1(dur), action: "", camera: "", size: "", lens: "", cast: [], dialogue: [], image_id: null });

export const fromServer = (beats: Beat[]): BeatDraft[] =>
  beats.map((b) => ({ key: b.id, id: b.id, dur: r1(b.end - b.start), action: b.action, camera: b.camera, size: b.size ?? "", lens: b.lens ?? "", cast: b.cast, dialogue: b.dialogue, image_id: b.image_id }));

export const total = (d: BeatDraft[]) => r1(d.reduce((s, b) => s + b.dur, 0));

/** Payload untuk PUT /scenes/{id}/beats: awal/akhir kumulatif dibulatkan 0,1 dtk. */
export function toPayload(d: BeatDraft[]) {
  let at = 0;
  return d.map((b) => {
    const start = r1(at);
    at += b.dur;
    return { ...(b.id ? { id: b.id } : {}), start, end: r1(at), action: b.action, camera: b.camera, size: b.size || null, lens: b.lens || null, cast: b.cast, dialogue: b.dialogue };
  });
}

/** Awal tiap beat (untuk label waktu dan penggaris). */
export const starts = (d: BeatDraft[]) => d.reduce<number[]>((a, b, i) => (a.push(i ? r1(a[i - 1] + d[i - 1].dur) : 0), a), []);

/** `n` beat sama panjang untuk durasi `totalSec`; sisa pembulatan ditaruh di beat terakhir. n dibatasi supaya tiap beat >= MIN_BEAT. */
export function equalSplit(totalSec: number, n: number): BeatDraft[] {
  const count = Math.max(1, Math.min(n, Math.floor(totalSec / MIN_BEAT)));
  const each = r1(Math.floor((totalSec / count) * 10) / 10);
  const out = Array.from({ length: count }, () => blank(each));
  out[count - 1].dur = r1(totalSec - each * (count - 1));
  return out;
}

/** Bagi beat `i` jadi dua di tengah (hanya bila cukup panjang). Isi (aksi, pemeran, gambar) tetap di bagian pertama. */
export function splitAt(d: BeatDraft[], i: number): BeatDraft[] | null {
  const b = d[i];
  if (!b || b.dur < MIN_BEAT * 2) return null;
  const first = r1(Math.round(b.dur / 2 / STEP) * STEP);
  const a = Math.min(Math.max(first, MIN_BEAT), b.dur - MIN_BEAT);
  return [...d.slice(0, i), { ...b, dur: r1(a) }, { ...blank(b.dur - a), cast: b.cast }, ...d.slice(i + 1)];
}

/** Gabung beat `i` dengan beat sesudahnya: durasi dijumlah, aksi digabung, pemeran/dialog digabung tanpa duplikat. */
export function mergeNext(d: BeatDraft[], i: number): BeatDraft[] | null {
  const a = d[i], b = d[i + 1];
  if (!a || !b) return null;
  const merged: BeatDraft = {
    ...a, dur: r1(a.dur + b.dur), action: [a.action, b.action].filter(Boolean).join(" Lalu ") || "",
    camera: a.camera || b.camera, cast: [...new Set([...a.cast, ...b.cast])], dialogue: [...a.dialogue, ...b.dialogue], image_id: a.image_id ?? b.image_id,
  };
  return [...d.slice(0, i), merged, ...d.slice(i + 2)];
}

/** Ubah durasi beat `i` dan serap selisihnya di beat sesudahnya (atau sebelumnya bila terakhir) agar total tetap. Null bila melanggar MIN_BEAT. */
export function resizeWithin(d: BeatDraft[], i: number, dur: number): BeatDraft[] | null {
  const j = i < d.length - 1 ? i + 1 : i - 1;
  if (j < 0) return null;
  const next = r1(dur);
  const other = r1(d[i].dur + d[j].dur - next);
  if (next < MIN_BEAT - 1e-9 || other < MIN_BEAT - 1e-9) return null;
  return d.map((b, n) => (n === i ? { ...b, dur: next } : n === j ? { ...b, dur: other } : b));
}

/** Geser batas antara beat `i` dan `i+1` ke `leftDur` (total berdua tetap). Dipakai seret dan panah keyboard. */
export function moveBoundary(d: BeatDraft[], i: number, leftDur: number): BeatDraft[] | null {
  if (i < 0 || i >= d.length - 1) return null;
  const sum = d[i].dur + d[i + 1].dur;
  if (sum < MIN_BEAT * 2 - 1e-9) return null;
  const left = Math.round(leftDur / STEP) * STEP;
  const l = Math.min(Math.max(left, MIN_BEAT), sum - MIN_BEAT);
  return d.map((b, n) => (n === i ? { ...b, dur: r1(l) } : n === i + 1 ? { ...b, dur: r1(sum - l) } : b));
}

/** Skala semua beat ke total baru secara proporsional (tiap beat >= MIN_BEAT; null bila total terlalu kecil). */
export function scaleTo(d: BeatDraft[], totalSec: number): BeatDraft[] | null {
  if (!d.length || totalSec < d.length * MIN_BEAT - 1e-9) return null;
  const cur = total(d) || 1;
  const out = d.map((b) => ({ ...b, dur: Math.max(MIN_BEAT, r1(Math.round(((b.dur * totalSec) / cur) / STEP) * STEP)) }));
  let diff = r1(totalSec - total(out));   // sisa pembulatan: ambil dari / berikan ke beat terpanjang yang masih bisa
  for (let guard = 0; Math.abs(diff) > 1e-9 && guard < 200; guard++) {
    const order = [...out.keys()].sort((x, y) => out[y].dur - out[x].dur);
    const pick = diff > 0 ? order[0] : order.find((k) => out[k].dur - STEP >= MIN_BEAT - 1e-9);
    if (pick === undefined) return null;
    const delta = diff > 0 ? Math.min(diff, STEP) : -Math.min(-diff, STEP);
    out[pick] = { ...out[pick], dur: r1(out[pick].dur + delta) };
    diff = r1(totalSec - total(out));
  }
  return Math.abs(diff) > 1e-9 ? null : out;
}

/** Perubahan isi yang berarti (untuk tanda belum disimpan); key React diabaikan. */
export const signature = (d: BeatDraft[]) => JSON.stringify(toPayload(d).map((b) => ({ ...b, id: undefined })));
