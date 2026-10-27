// Mention naskah episode (plan 15). Sintaks HARUS sama dengan backend/app/script.py: @[Nama karakter] dan #[Nama latar].

export const MENTION = /([@#])\[([^[\]\n]{1,80})\]/g;
export type MentionKind = "character" | "location";
export const kindOf = (sign: string): MentionKind => (sign === "@" ? "character" : "location");
export const key = (name: string) => name.trim().toLocaleLowerCase();

export type Piece = { text: string } | { mention: string; kind: MentionKind; name: string };

/** Pecah teks menjadi potongan biasa dan mention (untuk pratinjau berwarna). */
export function pieces(text: string): Piece[] {
  const out: Piece[] = [];
  let at = 0;
  for (const m of text.matchAll(MENTION)) {
    if (m.index! > at) out.push({ text: text.slice(at, m.index) });
    out.push({ mention: m[0], kind: kindOf(m[1]), name: m[2].trim() });
    at = m.index! + m[0].length;
  }
  if (at < text.length) out.push({ text: text.slice(at) });
  return out;
}

/** Token `@abc` / `#abc` (belum berkurung) tepat sebelum kursor; null bila tidak sedang mengetik mention. */
export function openToken(text: string, caret: number): { sign: "@" | "#"; query: string; start: number } | null {
  const m = /([@#])([^\s[\]@#]{0,30})$/.exec(text.slice(0, caret));
  if (!m) return null;
  const start = caret - m[0].length;
  if (start > 0 && /\S/.test(text[start - 1]) && !/[([{"'“]/.test(text[start - 1])) return null;   // bukan di tengah kata/alamat surel
  return { sign: m[1] as "@" | "#", query: m[2], start };
}
