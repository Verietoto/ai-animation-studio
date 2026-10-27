"""Perakit request Seedance untuk Storyboard v2 (plan 18 fase D + Revisi 4). MURNI: tanpa DB atau jaringan.

Keluaran mengikuti format prompt shot Seedance 2.0 (docs/reference/seedance-shot-format.md): blok global
FORMAT / SUBJECT / WARDROBE / ENVIRONMENT / MOOD, lalu `SHOT N — m:ss to m:ss, UKURAN, LENSA, GERAK. Aksi.`
Bagian tanpa isi dihilangkan, tidak dikarang.

Susunan referensi (urutan = penomoran `@image_N` / `@audio_N`; satu daftar akhir menjadi sumber tunggal penomoran dan legenda):
  1. gambar beat berurutan waktu (acuan bingkai tiap shot),
  2. satu gambar per karakter yang tampil,
  3. gambar latar,
  audio: suara karakter yang berdialog dan punya sampel (maks MAX_AUDIO).
Batas MAX_IMAGES: gambar beat tidak dibuang kecuali beat-nya sendiri melebihi batas (dijarangkan merata, awal dan akhir dijaga);
sisa tempat diisi karakter lebih dulu, baru latar. Setiap pembuangan menjadi peringatan.

Belum terbukti: notasi `@image_N`, timestamp `m:ss`, dan tipe `audio_url` belum diuji lewat OpenRouter (spike dilewati, kredit habis).
Seluruh format ada di fungsi ini, jadi perbaikannya satu tempat.
"""
import re

MAX_IMAGES = 9
MAX_AUDIO = 3
DESC_CLIP = 200


def _clip(text: str | None, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _thin(items: list, keep: int) -> list:
    """Pilih `keep` item merata dari `items`, selalu menyertakan yang pertama dan terakhir."""
    if keep >= len(items):
        return list(items)
    if keep == 1:
        return [items[0]]
    idx = sorted({round(i * (len(items) - 1) / (keep - 1)) for i in range(keep)})
    return [items[i] for i in idx]


def _t(x: float) -> str:
    return f"{x:g}"


def ts(x: float) -> str:
    """Detik → `m:ss` (pecahan 0.5 dtk menjadi `m:ss.5`)."""
    whole, frac = divmod(round(x * 10), 10)
    return f"{whole // 60}:{whole % 60:02d}" + (f".{frac}" if frac else "")


def build(*, beats: list[dict], cast: list[dict], location: dict | None, voices: dict[str, dict], style: str = "", genre: str = "",
          mood: str = "", fallback_action: str = "", use_audio: bool = True, previs: bool = False,
          max_images: int = MAX_IMAGES) -> dict:
    """Mengembalikan {"refs": [...], "prompt": str, "warnings": [str]}.

    beats   : [{start, end, action, camera, size?, lens?, cast:[character_id], dialogue:[{character_id,text}], image_id}] berurutan
    cast    : [{character_id, name, description, image_id, wardrobe?}]   (wardrobe = teks tampilan/outfit)
    location: {name, description, image_id} atau None
    voices  : {character_id: {description, has_audio, voice_id}} (suara aktif; boleh kosong)
    refs    : [{"kind": "image"|"audio"|"video", "n": nomor dalam jenisnya, "image_id"|"voice_id", "label": str}]
    """
    warnings: list[str] = []
    names = {c["character_id"]: c["name"] for c in cast}

    # ---- gambar ----
    beat_imgs = [(i, b) for i, b in enumerate(beats, 1) if b.get("image_id")]
    if len(beat_imgs) > max_images:
        dropped = len(beat_imgs) - max_images
        beat_imgs = _thin(beat_imgs, max_images)
        warnings.append(f"{dropped} gambar beat tidak dikirim (batas {max_images} gambar); beatnya tetap ada di prompt teks")
    room = max_images - len(beat_imgs)
    chars = [c for c in cast if c.get("image_id")]
    kept_chars = chars[:max(room, 0)]
    if len(kept_chars) < len(chars):
        warnings.append("gambar karakter " + ", ".join(c["name"] for c in chars[len(kept_chars):]) + " tidak dikirim (batas gambar penuh)")
    room -= len(kept_chars)
    use_loc = bool(location and location.get("image_id")) and room > 0
    if location and location.get("image_id") and not use_loc:
        warnings.append(f"gambar latar {location['name']} tidak dikirim (batas gambar penuh)")

    refs: list[dict] = []
    keyframes: list[str] = []
    char_ref: dict[str, int] = {}
    beat_n: dict[int, int] = {}
    loc_n = 0
    for i, b in beat_imgs:
        n = len(refs) + 1
        beat_n[i] = n
        refs.append({"kind": "image", "n": n, "image_id": b["image_id"], "label": f"keyframe shot {i} ({_t(b['start'])}-{_t(b['end'])}s)"})
        keyframes.append(f"@image_{n} — keyframe of shot {i}")
    for c in kept_chars:
        n = len(refs) + 1
        char_ref[c["character_id"]] = n
        refs.append({"kind": "image", "n": n, "image_id": c["image_id"], "label": f"karakter {c['name']}"})
    if use_loc:
        loc_n = len(refs) + 1
        refs.append({"kind": "image", "n": loc_n, "image_id": location["image_id"], "label": f"latar {location['name']}"})

    # ---- suara ----
    speakers = list(dict.fromkeys(d["character_id"] for b in beats for d in b.get("dialogue", []) if d.get("character_id") in names))
    audio_n = 0
    voice_lines: list[str] = []
    for cid in speakers:
        v = voices.get(cid) or {}
        if use_audio and v.get("has_audio") and audio_n < MAX_AUDIO:
            audio_n += 1
            refs.append({"kind": "audio", "n": audio_n, "voice_id": v["voice_id"], "label": f"suara {names[cid]}"})
            voice_lines.append(f"@audio_{audio_n} — the voice of {names[cid]}" + (f" ({_clip(v.get('description'), 100)})" if v.get("description") else ""))
        elif v.get("description"):
            voice_lines.append(f"{names[cid]}'s voice: {_clip(v['description'], 120)}")
        elif v.get("has_audio") and not use_audio:
            warnings.append(f"sampel suara {names[cid]} tidak dikirim (tanpa hosting publik); model memilih suaranya sendiri")
    if use_audio and sum(1 for cid in speakers if (voices.get(cid) or {}).get("has_audio")) > MAX_AUDIO:
        warnings.append(f"hanya {MAX_AUDIO} sampel suara yang bisa dikirim; penutur lain memakai deskripsi suara")

    video_line = ""
    if previs:
        refs.append({"kind": "video", "n": 1, "label": "video previs 3D"})
        video_line = "@video_1 — rough 3D previs; copy its camera movement, framing and timing, but NOT the mannequin look"

    # ---- prompt: blok global ----
    total = beats[-1]["end"] if beats else 0
    fmt = [f"{_t(total)}s"] if total else []
    if beats:
        fmt.append(f"{len(beats)} SHOT" + ("S" if len(beats) > 1 else ""))
    if genre.strip():
        fmt.append(_clip(genre, 80))
    parts: list[str] = []
    if fmt:
        parts.append("FORMAT: " + " / ".join(fmt))

    subject = []
    for c in cast:
        ref = f"@image_{char_ref[c['character_id']]} — " if c["character_id"] in char_ref else ""
        desc = _clip(c.get("description"), DESC_CLIP)
        subject.append(f"{ref}{c['name']}" + (f", {desc}" if desc else ""))
    if subject:
        parts.append("SUBJECT: " + " ".join(s.rstrip(".") + "." for s in subject))
    wardrobe = [f"{c['name']}: {_clip(c['wardrobe'], DESC_CLIP)}" for c in cast if c.get("wardrobe")]
    if wardrobe:
        parts.append("WARDROBE: " + " ".join(w.rstrip(".") + "." for w in wardrobe))
    if location:
        env = location["name"] + (f". {_clip(location.get('description'), 300).rstrip('.')}" if location.get("description") else "")
        parts.append("ENVIRONMENT: " + env + (f". Reference: @image_{loc_n}" if loc_n else "") + ".")
    mood_text = _clip(mood, 300) or _clip(style, 300)
    if mood_text:
        parts.append("MOOD: " + mood_text.rstrip(".") + ".")
    extra = [*keyframes, *voice_lines, *([video_line] if video_line else [])]
    if extra:
        parts.append("REFERENCES: " + "; ".join(extra) + ".")

    # ---- daftar shot ----
    if beats:
        parts.append("")
        for i, b in enumerate(beats, 1):
            head = [f"SHOT {i} — {ts(b['start'])} to {ts(b['end'])}"]
            tech = [x for x in ((b.get("size") or "").strip(), f"{b['lens']}mm" if b.get("lens") else "", _clip(b.get("camera"), 120)) if x]
            line = ", ".join([head[0], *tech]) + "."
            body = [_clip(b.get("action"), 300).rstrip(".")] if (b.get("action") or "").strip() else []
            who = [names[c] for c in b.get("cast", []) if c in names]
            if who and not body:
                body.append(", ".join(who) + " in frame")
            lines = [f'{names.get(d["character_id"], "Someone")} says: "{_clip(d["text"], 300)}"' for d in b.get("dialogue", []) if d.get("text", "").strip()]
            text = ". ".join(body + lines)
            if i in beat_n:
                text += (". " if text else "") + f"Match @image_{beat_n[i]}"
            parts.append(f"{line} {text}." if text else line)
    elif fallback_action.strip():
        parts.append(_clip(fallback_action, 800))
    tail = "Keep every character consistent with its reference image. Smooth continuous motion, cinematic."
    parts.append("\n" + tail)
    return {"refs": refs, "prompt": "\n".join(parts), "warnings": warnings, "tail": tail,
            "references": ("REFERENCES: " + "; ".join([*voice_lines, *([video_line] if video_line else [])]) + ".") if (voice_lines or video_line) else "",
            "map": {"characters": {c["name"]: char_ref[c["character_id"]] for c in cast if c["character_id"] in char_ref}, "location": loc_n}}


_MENTION = re.compile(r"([@#])\[([^\[\]\n]{1,80})\]")
_LABEL = re.compile(r"^\s*(SUBJECT|ENVIRONMENT)\s*:", re.I)


def resolve(text: str, *, characters: dict[str, int], location: int, known_locations: set[str]) -> str:
    """Prompt adegan (mention `@[Nama]` / `#[Latar]`) → teks untuk Seedance. Nomor `@image_N` ditentukan dari daftar referensi AKTUAL
    (`characters` nama→n, `location` n atau 0), jadi tidak pernah basi. Di baris SUBJECT, karakter pertama kali disebut menjadi
    `@image_N — Nama`; di baris ENVIRONMENT latar menjadi `Nama (see @image_N)`; selain itu hanya nama biasa."""
    by = {k.casefold(): n for k, n in characters.items()}
    out = []
    for line in text.split("\n"):
        label = (_LABEL.match(line) or [None, ""])[1].upper() if _LABEL.match(line) else ""
        done: set[str] = set()

        def sub(m: re.Match) -> str:
            kind, name = m.group(1), m.group(2).strip()
            k = name.casefold()
            if kind == "@" and label == "SUBJECT" and k in by and k not in done:
                done.add(k)
                return f"@image_{by[k]} — {name}"
            if kind == "#" and label == "ENVIRONMENT" and location and k not in done:
                done.add(k)
                return f"{name} (see @image_{location})"
            return name
        out.append(_MENTION.sub(sub, line))
    return "\n".join(out)
