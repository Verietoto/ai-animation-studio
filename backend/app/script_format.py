"""Pengurai naskah berformat shot Seedance 2.0 (plan 18 Revisi 5). MURNI: tanpa DB/HTTP.

Satu blok per adegan (maks 15 dtk), format docs/reference/seedance-shot-format.md dengan sintaks mention proyek ini:

    ADEGAN 1 — #[Dapur]
    FORMAT: 12s / 5 SHOTS / komedi
    SUBJECT: @[Momon], kucing oren
    WARDROBE: Momon: syal merah
    ENVIRONMENT: #[Dapur], pagi
    MOOD: hangat
    SHOT 1 — 0:00 to 0:02, WS, 24mm, locked. @[Momon] masuk.
    SHOT 2 — 0:02 to 0:04, MS, 35mm, slow push-in. @[Momon] says: "Lapar"

`parse` mengubahnya jadi draf adegan (bentuk sama dengan `script.clean_split` + kunci `beats`) dan daftar galat per adegan.
Tidak ada entitas baru: nama yang tidak dikenal hanya jadi peringatan.
"""
import math
import re

from . import beats as beats_mod
from . import script
from .service import ServiceError

MAX_SCENE_SECONDS = 15
LABELS = ("FORMAT", "SUBJECT", "WARDROBE", "ENVIRONMENT", "MOOD")
HEADER = re.compile(r"^\s*(?:ADEGAN|SCENE)\b", re.I)
LABEL = re.compile(r"^\s*(FORMAT|SUBJECT|WARDROBE|ENVIRONMENT|MOOD)\s*:\s*(.*)$", re.I)
TIME = r"(\d+):(\d{2})(?:\.(\d))?"
SHOT = re.compile(rf"^\s*SHOT\s+(\d+)\s*[—–-]\s*{TIME}\s+to\s+{TIME}\s*(.*)$", re.I)
SAY = re.compile(r'@\[([^\[\]\n]{1,80})\]\s+says\s*:\s*"([^"\n]*)"', re.I)
LENS = re.compile(r"^(\d{2,3})\s*mm$", re.I)
FORMAT_SECONDS = re.compile(r"(\d+(?:\.\d)?)\s*s\b", re.I)
FORMAT_SHOTS = re.compile(r"(\d+)\s*SHOTS?\b", re.I)


def _secs(m: tuple) -> float:
    minutes, sec, tenth = m
    return int(minutes) * 60 + int(sec) + (int(tenth) / 10 if tenth else 0)


def is_formatted(text: str) -> bool:
    """Naskah dianggap berformat bila ada minimal satu baris FORMAT: dan satu baris SHOT n — m:ss to m:ss."""
    lines = (text or "").splitlines()
    return any(re.match(r"^\s*FORMAT\s*:", l, re.I) for l in lines) and any(SHOT.match(l) for l in lines)


def _blocks(text: str) -> tuple[list[list[str]], list[str]]:
    """Pecah per adegan. Blok baru dimulai di `ADEGAN`/`SCENE`, atau di FORMAT: bila blok berjalan sudah punya FORMAT/SHOT."""
    blocks, cur, stray, loose = [], [], [], []
    seen = False
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        starts = bool(HEADER.match(line)) or (bool(LABEL.match(line)) and LABEL.match(line).group(1).upper() == "FORMAT" and seen)
        if starts and cur and (seen or not HEADER.match(line) or any(LABEL.match(l) or SHOT.match(l) for l in cur)):
            if seen:
                blocks.append(cur)
                cur, seen = [], False
        if HEADER.match(line) or LABEL.match(line) or SHOT.match(line):
            cur.append(line)
            seen = seen or bool(LABEL.match(line) or SHOT.match(line))
        elif cur:
            cur.append(line)   # lanjutan baris sebelumnya (nilai label yang melipat)
        elif line.strip():
            stray.append(line.strip())
    if cur and seen:
        blocks.append(cur)
    return blocks, stray


def _resolve(names: list[str], pool: dict[str, str], unknown: set[str]) -> list[str]:
    ids = []
    for n in names:
        i = pool.get(script.key(n))
        if i is None:
            unknown.add(n)
        elif i not in ids:
            ids.append(i)
    return ids


def _scene(n: int, lines: list[str], chars: dict[str, str], locs: dict[str, str], char_names: dict[str, str], warnings: list[str]) -> dict:
    where = f"adegan {n}"
    fields: dict[str, str] = {}
    shots: list[dict] = []
    last = None
    header = ""
    for line in lines:
        if HEADER.match(line):
            header = line
            last = None
            continue
        if (m := SHOT.match(line)):
            g = m.groups()
            shots.append({"no": int(g[0]), "start": _secs(g[1:4]), "end": _secs(g[4:7]), "rest": g[7].strip()})
            last = ("shot", shots[-1])
        elif (m := LABEL.match(line)):
            key = m.group(1).upper()
            fields[key] = m.group(2).strip()
            last = ("field", key)
        elif last and line.strip():
            if last[0] == "shot":
                last[1]["rest"] += " " + line.strip()
            else:
                fields[last[1]] += " " + line.strip()
    if not shots:
        raise ServiceError(f"{where}: tidak ada baris SHOT", 422)
    missing = [l for l in ("FORMAT", "SUBJECT", "ENVIRONMENT") if l not in fields]
    if missing:
        raise ServiceError(f"{where}: label {', '.join(missing)} belum ada", 422)

    unknown: set[str] = set()
    loc_names = [m.group(2).strip() for m in script.MENTION.finditer(header + " " + fields.get("ENVIRONMENT", "")) if m.group(1) == "#"]
    loc_ids = _resolve(loc_names, locs, unknown)
    if loc_names and not loc_ids:
        warnings.append(f"{where}: latar #[{loc_names[0]}] tidak ada di episode, dikosongkan")
    scene_cast = _resolve([nm for k, nm in script.mentions(fields.get("SUBJECT", "")) if k == "character"], chars, unknown)

    items = []
    for s in shots:
        rest = s["rest"]
        size = lens = None
        camera = ""
        action = rest
        if rest.startswith(","):
            head, _, action = rest[1:].partition(". ") if ". " in rest else (rest[1:].rstrip("."), "", "")
            tech = [t.strip() for t in head.split(",") if t.strip()]
            rest_tech = []
            for t in tech:
                if t.upper() in beats_mod.SIZES and size is None:
                    size = t.upper()
                elif (lm := LENS.match(t)) and lens is None:
                    lens = lm.group(1)
                else:
                    rest_tech.append(t)
            camera = ", ".join(rest_tech)
        else:
            action = rest.lstrip(". ").strip() if rest.startswith(".") else rest
        dialogue, said = [], set()
        for dm in SAY.finditer(action):
            cid = chars.get(script.key(dm.group(1)))
            if cid is None:
                unknown.add(dm.group(1).strip())
                continue
            dialogue.append({"character_id": cid, "text": dm.group(2).strip()})
            said.add(cid)
        action = SAY.sub("", action)
        cast_names = [m.group(2).strip() for m in script.MENTION.finditer(action) if m.group(1) == "@"]
        in_frame = _resolve(cast_names, chars, unknown)
        for cid in said:
            if cid not in in_frame:
                in_frame.append(cid)
        action = script.MENTION.sub(lambda m: m.group(2).strip(), action)
        action = " ".join(action.replace(" ,", ",").split()).strip(" .")
        if len(action) > beats_mod.ACTION_MAX:
            warnings.append(f"{where}, shot {s['no']}: aksi dipotong {beats_mod.ACTION_MAX} karakter")
            action = action[:beats_mod.ACTION_MAX].rstrip()
        items.append({"start": s["start"], "end": s["end"], "size": size, "lens": lens, "camera": camera, "action": action,
                      "cast": in_frame, "dialogue": dialogue})
        for cid in in_frame:
            if cid not in scene_cast:
                scene_cast.append(cid)
    for u in sorted(unknown):
        warnings.append(f"{where}: \"{u}\" tidak ada di episode, dilepas")
    if len(scene_cast) > script.MAX_CAST:
        raise ServiceError(f"{where}: {len(scene_cast)} pemeran; maksimal {script.MAX_CAST} per adegan", 422)

    total = items[-1]["end"]
    if total > MAX_SCENE_SECONDS + 1e-9:
        raise ServiceError(f"{where}: {total:g} dtk melebihi {MAX_SCENE_SECONDS} dtk (batas satu video Seedance); bagi jadi beberapa adegan", 422)
    declared = FORMAT_SECONDS.search(fields["FORMAT"])
    planned = float(declared.group(1)) if declared else total
    shots_declared = FORMAT_SHOTS.search(fields["FORMAT"])
    if shots_declared and int(shots_declared.group(1)) != len(items):
        warnings.append(f"{where}: FORMAT menyebut {shots_declared.group(1)} shot, ada {len(items)}")
    try:
        cleaned, w = beats_mod.clean(items, set(scene_cast), planned)
    except ServiceError as exc:
        raise ServiceError(f"{where}: {exc}", 422) from exc
    warnings.extend(f"{where}: {x}" for x in w)
    for b in cleaned:
        b["image_id"] = None
    dialogue_lines = [f"{char_names.get(d['character_id'], '?')}: {d['text']}" for b in cleaned for d in b["dialogue"]]
    return {"location_id": loc_ids[0] if loc_ids else None, "time_of_day": "", "camera": cleaned[0]["camera"],
            "dialogue": "\n".join(dialogue_lines)[:script.FIELD_LIMITS["dialogue"]],
            "extra_prompt": fields.get("MOOD", "")[:script.FIELD_LIMITS["extra_prompt"]],
            "planned_seconds": max(1, math.ceil(max(planned, total) - 1e-9)),
            "excerpt": "\n".join(lines).strip()[:script.FIELD_LIMITS["excerpt"]],
            "cast": [{"character_id": c, "outfit_id": None, "action": ""} for c in scene_cast], "beats": cleaned}


def parse(text: str, characters: list[dict], locations: list[dict]) -> dict:
    """{"scenes": [...], "warnings": [...], "errors": [...]}. `errors` berisi satu pesan per adegan yang gagal; adegan lain tetap diurai."""
    chars = {script.key(c["name"]): c["id"] for c in characters}
    locs = {script.key(l["name"]): l["id"] for l in locations}
    names = {c["id"]: c["name"] for c in characters}
    blocks, stray = _blocks(text)
    scenes, warnings, errors = [], [], []
    for n, block in enumerate(blocks, 1):
        try:
            scenes.append(_scene(n, block, chars, locs, names, warnings))
        except ServiceError as exc:
            errors.append(str(exc))
    if stray:
        warnings.append(f"{len(stray)} baris di luar blok adegan diabaikan")
    if not blocks:
        errors.append("tidak ada blok adegan berformat (butuh FORMAT: dan SHOT n — m:ss to m:ss)")
    return {"scenes": scenes, "warnings": warnings, "errors": errors}


def _norm(block: list[str]) -> str:
    """Isi blok tanpa baris judul ADEGAN (nomor boleh bergeser) dan tanpa beda spasi."""
    return " ".join(" ".join(l for l in block if not HEADER.match(l)).split())


def compare(old: str, new: str) -> dict:
    """Bandingkan dua naskah per blok adegan. Pencocokan berdasarkan ISI, bukan nomor (adegan disisip/dihapus tidak menggeser tanda).
    -> {"scenes": [{"n", "changed", "text", "previous"}], "previous_scenes": int, "removed": int}"""
    old_blocks, _ = _blocks(old)
    new_blocks, _ = _blocks(new)
    pool: dict[str, int] = {}
    for b in old_blocks:
        pool[_norm(b)] = pool.get(_norm(b), 0) + 1
    scenes = []
    for n, b in enumerate(new_blocks, 1):
        key = _norm(b)
        same = pool.get(key, 0) > 0
        if same:
            pool[key] -= 1
        prev = "\n".join(old_blocks[n - 1]).strip() if (not same and n <= len(old_blocks)) else None
        scenes.append({"n": n, "changed": not same, "text": "\n".join(b).strip(), "previous": prev})
    return {"scenes": scenes, "previous_scenes": len(old_blocks), "removed": sum(pool.values())}
