"""Susunan blockout 3D untuk previs adegan (plan 14, versi 2 di plan 17): validasi data dan prompt untuk AI penyusun.

Modul murni tanpa DB/HTTP. Susunan = data; three.js di browser yang menggambarnya. Kosakata (bentuk, objek siap pakai, jenis tubuh,
sendi, pose, waktu) dibaca dari `shared/blockout_vocabulary.json` lewat `vocab`, satu sumber dengan frontend. Batas sudut tiap sendi
diterapkan frontend saat pose dipasang; server menjaga struktur, rentang angka, daftar nama, dan referensi antar objek.
Susunan versi 1 (hanya manusia, tiga bentuk properti) tetap diterima dan dinaikkan ke versi 2.
"""
import json
import math
import re

from . import vocab
from .service import ServiceError

MAX_KEYS, MAX_PROPS, MAX_ACTORS, MAX_BYTES = 12, 120, 3, 128 * 1024
MAX_DURATION = 15          # detik; sama dengan batas durasi Seedance reference
DEFAULT_DURATION = 5
COORD, SCALE = 100.0, 50.0
ID_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
WALLS = ("north", "south", "east", "west")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _num(value, what: str, lo: float, hi: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise ServiceError(f"susunan 3D: {what} harus angka {lo:g} sampai {hi:g}", 422)
    return float(value)


def _vec(value, what: str, lim: float, lo: float | None = None) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ServiceError(f"susunan 3D: {what} harus [x, y, z]", 422)
    return [round(_num(v, what, -lim if lo is None else lo, lim), 3) for v in value]


def _keys(raw, what: str, duration: float, one) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise ServiceError(f"susunan 3D: {what} butuh minimal satu key", 422)
    if len(raw) > MAX_KEYS:
        raise ServiceError(f"susunan 3D: {what} maksimal {MAX_KEYS} key", 422)
    keys: dict[float, dict] = {}
    for k in raw:
        if not isinstance(k, dict):
            raise ServiceError(f"susunan 3D: key {what} tidak valid", 422)
        t = round(_num(k.get("t"), f"{what}.t", 0, duration), 3)
        keys[t] = one(k)          # t ganda: yang terakhir menang
        keys[t]["t"] = t
    return [keys[t] for t in sorted(keys)]


def _prop_ids(raw_props: list) -> list[str]:
    """Id stabil per properti: dipakai bila valid dan unik, selain itu dibuat `p<n>`."""
    seen: set[str] = set()
    out = []
    for n, p in enumerate(raw_props, 1):
        pid = p.get("id") if isinstance(p, dict) else None
        if not isinstance(pid, str) or not ID_RE.match(pid) or pid in seen:
            pid = f"p{n}"
            while pid in seen:
                pid += "x"
        seen.add(pid)
        out.append(pid)
    return out


def _prop(p, pid: str, known: set[str], warnings: list[str], v1: bool = False) -> dict:
    types = vocab.prop_types()
    if not isinstance(p, dict) or p.get("type") not in types:
        raise ServiceError(f"susunan 3D: jenis properti harus salah satu dari {types}", 422)
    is_shape = p["type"] in vocab.shapes()
    out: dict = {"id": pid, "type": p["type"]}
    if p.get("label") is not None:
        out["label"] = str(p["label"]).strip()[:40]
    color = p.get("color", "#8a8a8a" if is_shape else None)
    if color is not None:
        if not isinstance(color, str) or not HEX.match(color):
            raise ServiceError("susunan 3D: warna properti harus #rrggbb", 422)
        out["color"] = color
    mat = p.get("material")
    if isinstance(mat, dict):
        out["material"] = {k: round(_num(mat[k], f"material.{k}", 0, 1), 3) for k in ("roughness", "emissive") if k in mat}
    rot = _vec(p.get("rot", [0, 0, 0]), "prop.rot", 360)
    if "rot_y" in p:
        rot[1] = round(_num(p["rot_y"], "prop.rot_y", -360, 360), 3)
    out["rot"] = rot
    scale = p.get("scale", 1)
    out["scale"] = round(_num(scale, "prop.scale", 0.05, SCALE), 3) if isinstance(scale, (int, float)) and not isinstance(scale, bool) \
        else _vec(scale, "prop.scale", SCALE, lo=0.02)
    if is_shape:
        out["size"] = _vec(p.get("size", [1, 1, 1]), "prop.size", SCALE, lo=0.02)
    for k, lim in (("dx", COORD), ("dz", COORD), ("offset", COORD), ("angle", 360)):
        if k in p:
            out[k] = round(_num(p[k], f"prop.{k}", -lim, lim), 3)
    if "dist" in p:
        out["dist"] = round(_num(p["dist"], "prop.dist", 0, COORD), 3)
    # penempatan: pos (mutlak) > on > against > near > at; relasi ke id yang tidak ada diturunkan jadi `at [0,0]` dengan peringatan
    if "pos" in p:
        out["pos"] = _vec(p["pos"], "prop.pos", COORD)
        if v1 and is_shape:   # v1: pos = titik tengah bentuk; v2: pos = titik tengah ALAS
            sc = out["scale"] if isinstance(out["scale"], list) else [out["scale"]] * 3
            out["pos"][1] = round(out["pos"][1] - out["size"][1] * sc[1] / 2, 3)
    elif p.get("on") in known and p["on"] != pid:
        out["on"] = p["on"]
    elif p.get("against") in WALLS:
        out["against"] = p["against"]
    elif p.get("near") in known and p["near"] != pid:
        out["near"] = p["near"]
    elif isinstance(p.get("at"), (list, tuple)) and len(p["at"]) == 2:
        out["at"] = [round(_num(v, "prop.at", -COORD, COORD), 3) for v in p["at"]]
    else:
        if any(k in p for k in ("on", "near", "against")):
            warnings.append(f"properti {pid}: relasi penempatan tidak valid (target tidak ada), ditaruh di tengah")
        out["at"] = [0.0, 0.0]
    return out


def clean_report(raw, cast_ids: list[str], set_ids: tuple | list | set = ()) -> tuple[dict, list[str]]:
    """Validasi + normalisasi susunan (v1 atau v2) jadi v2; melempar ServiceError 422. Mengembalikan (susunan, peringatan)."""
    if not isinstance(raw, dict):
        raise ServiceError("susunan 3D harus objek", 422)
    if len(json.dumps(raw)) > MAX_BYTES:
        raise ServiceError(f"susunan 3D terlalu besar (maks {MAX_BYTES // 1024} KB)", 422)
    warnings: list[str] = []
    duration = round(_num(raw.get("duration", DEFAULT_DURATION), "duration", 1, MAX_DURATION), 3)

    env_raw = raw.get("environment") if isinstance(raw.get("environment"), dict) else {}
    env = {}
    for key, table in (("time", vocab.load()["times"]), ("weather", vocab.load()["weather"])):
        if env_raw.get(key) is not None:
            if env_raw[key] in table:
                env[key] = env_raw[key]
            else:
                warnings.append(f"lingkungan: {key} {env_raw[key]!r} tidak dikenal, diabaikan")

    def cam(k):
        return {"pos": _vec(k.get("pos"), "camera.pos", COORD), "target": _vec(k.get("target"), "camera.target", COORD),
                "mm": round(_num(k.get("mm", 35), "camera.mm", 10, 200), 1)}

    actors, seen = [], set()
    for a in raw.get("actors") or []:
        cid = a.get("character_id") if isinstance(a, dict) else None
        if cid not in cast_ids:
            raise ServiceError("susunan 3D: aktor harus pemeran adegan ini", 422)
        if cid in seen:
            raise ServiceError("susunan 3D: satu pemeran hanya boleh satu aktor", 422)
        seen.add(cid)
        body_name = a.get("body", "humanoid")
        body = vocab.bodies().get(body_name)
        if body is None:
            raise ServiceError(f"susunan 3D: jenis tubuh tidak dikenal: {body_name!r}; pilihan {list(vocab.bodies())}", 422)

        def actor_key(k, body=body):
            pose = k.get("pose", "stand")
            if pose not in body["poses"]:
                raise ServiceError(f"susunan 3D: pose tidak dikenal: {pose!r}; pilihan {list(body['poses'])}", 422)
            joints = k.get("joints") or {}
            if not isinstance(joints, dict):
                raise ServiceError("susunan 3D: joints harus objek", 422)
            out = {}
            for name, rot in joints.items():
                if name not in body["joints"]:
                    raise ServiceError(f"susunan 3D: sendi tidak dikenal: {name!r}", 422)
                out[name] = _vec(rot, f"joints.{name}", 180)
            return {"pos": _vec(k.get("pos"), "actor.pos", COORD), "facing": round(_num(k.get("facing", 0), "actor.facing", -360, 360), 1),
                    "pose": pose, "joints": out}
        actors.append({"character_id": cid, "body": body_name, "keys": _keys(a.get("keys"), "actor", duration, actor_key)})
    if len(actors) > MAX_ACTORS:
        raise ServiceError(f"susunan 3D: maksimal {MAX_ACTORS} aktor", 422)

    raw_props = raw.get("props") or []
    if not isinstance(raw_props, list):
        raise ServiceError("susunan 3D: props harus daftar", 422)
    if len(raw_props) > MAX_PROPS:
        raise ServiceError(f"susunan 3D: maksimal {MAX_PROPS} properti", 422)
    ids = _prop_ids(raw_props)
    known = set(ids) | set(set_ids)
    v1 = raw.get("version") != 2
    props = [_prop(p, pid, known, warnings, v1) for p, pid in zip(raw_props, ids)]
    return ({"version": 2, "duration": duration, "environment": env,
             "camera": {"keys": _keys((raw.get("camera") or {}).get("keys"), "camera", duration, cam)},
             "actors": actors, "props": props}, warnings)


def clean(raw, cast_ids: list[str], set_ids: tuple | list | set = ()) -> dict:
    return clean_report(raw, cast_ids, set_ids)[0]


def _vocab_lines() -> str:
    prefabs = "\n".join(f"  - {n}: {p['size'][0]}x{p['size'][1]}x{p['size'][2]} m{', flat top (things can sit on it)' if p.get('top') else ''}"
                        f"{', mounted on a wall at ' + str(p['elevation']) + ' m' if p.get('elevation') else ''}" for n, p in vocab.prefabs().items())
    bodies = "\n".join(f"  - {n}: poses {list(b['poses'])}; joints {b['joints']}" for n, b in vocab.bodies().items())
    return f"Props (type): shapes {vocab.shapes()} (use size [w,h,d]) or ready-made objects:\n{prefabs}\nBody kinds:\n{bodies}"


SYSTEM = f"""You are a film previsualization assistant. You stage ONE scene as JSON for a three.js viewer. The world is rough but rich:
build the set the location description implies, and stage every character as the kind of body they are.
World: meters, Y is up, the floor is y=0, the origin is the middle of the floor, +Z points toward the default viewer. A standing person is
about 1.7 m tall; a cat about 0.3 m at the shoulder. Actor facing is degrees around Y: 0 = looking toward +Z, 90 = +X, 180 = -Z, 270 = -X.
{_vocab_lines()}
Characters: set "body" from the character description (a cat/dog/horse = quadruped; people, robots with arms and legs = humanoid). Use
only the poses and joints of that body. Moving between two positions = two keys (a gait cycle is added automatically).
Placing props: NEVER write y. Use ONE placement per prop: "at": [x, z] on the floor; "on": "<id of another prop>" (sits on its flat top,
optional "dx","dz"); "against": "north"|"south"|"east"|"west" (against that wall of the 14 x 12 m area, optional "offset" along the wall);
"near": "<id>" (optional "dist", "angle"). Give every prop a short unique "id" (lowercase, digits, - or _) and, when useful, a "label".
Optional "rot_y" (degrees), "scale" (number), "color" (#rrggbb), "material" {{"roughness":0-1,"emissive":0-1}} (emissive for lit lamps/screens).
Keep the stage uncluttered: 6-30 props that the description and actions imply, nothing overlapping on purpose.
"environment": {{"time": one of {list(vocab.load()['times'])}, "weather": one of {list(vocab.load()['weather'])}}} from the time of day.
Camera: mm between 18 (wide) and 85 (close); point target at the subject's chest (or a cat's back); keep every actor in frame.
Times are seconds from 0 to duration; at most {MAX_KEYS} keys per track. Give every character in the cast exactly one actor entry with their character_id.
Answer with the JSON object only."""


def user_prompt(ctx: dict) -> str:
    """ctx: {duration, ratio, location, time_of_day, camera, dialogue, extra, cast: [{character_id, name, description, action}], set_objects?}"""
    cast = "\n".join(f"- character_id={c['character_id']} name={c['name']}"
                     f"{' :: ' + c['description'][:200] if c.get('description') else ''} :: action: {c['action'] or '(none)'}" for c in ctx["cast"]) or "- (no characters)"
    loc = ctx["location"]
    where = f"{loc['name']}{' - ' + loc['description'] if loc and loc.get('description') else ''}" if loc else "(unspecified)"
    set_note = ""
    if ctx.get("set_objects"):
        listing = "\n".join(f"  - {o['id']}: {o['type']}{' (' + o['label'] + ')' if o.get('label') else ''}" for o in ctx["set_objects"][:60])
        set_note = (f"\nThe location already has this set; do NOT recreate it, you may refer to these ids in \"on\"/\"near\" and add only extra props "
                    f"the action needs:\n{listing}")
    return (f"Duration: {ctx['duration']} s. Aspect ratio: {ctx['ratio']}.\nLocation: {where}{set_note}\n"
            f"Time of day: {ctx['time_of_day'] or '(unspecified)'}\nCamera: {ctx['camera'] or '(unspecified)'}\n"
            f"Dialogue: {ctx['dialogue'] or '(none)'}\nExtra: {ctx['extra'] or '(none)'}\nCast:\n{cast}\n"
            'JSON shape: {"version":2,"duration":N,"environment":{"time":"senja","weather":"cerah"},'
            '"camera":{"keys":[{"t":0,"pos":[x,y,z],"target":[x,y,z],"mm":35}]},'
            '"actors":[{"character_id":"...","body":"humanoid","keys":[{"t":0,"pos":[x,0,z],"facing":0,"pose":"stand","joints":{}}]}],'
            '"props":[{"id":"meja1","type":"table","label":"meja panjang","against":"north"},{"id":"cangkir1","type":"cup","on":"meja1"}]}')
