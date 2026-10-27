"""Prompt adegan = sumber tunggal Storyboard v2 (plan 18 Revisi 8).

`render` (murni) menulis data adegan (latar, pemeran, beat, mood, durasi) sebagai blok berformat Seedance; kebalikannya adalah
`script_format.parse`. `ScenePrompt.put` menyimpan teks lalu MENURUNKAN latar, pemeran, beat, MOOD, dan durasi darinya.
Setiap jalur lain yang mengubah data itu mengosongkan `scenes.prompt` sehingga `get` merendernya ulang dari data (tidak pernah basi).
"""
from __future__ import annotations

import math
import re

from . import script, script_format, textai
from .seedance_request import ts
from .service import DEFAULT_WS, ServiceError

PROMPT_MAX = 4000
DESC_CLIP = 200


def _mention(name: str) -> str:
    return f"@[{name}]"


def _action_text(action: str, cast_names: list[str]) -> str:
    """Sisipkan mention untuk pemeran beat. Nama yang sudah ada di aksi dijadikan mention di tempat; yang belum, diawali di depan
    (aksi baru berbunyi "Nama aksi", sehingga render → urai → render stabil dan tidak menumpuk)."""
    text = action.strip().rstrip(".")
    for name in cast_names:
        hit = re.search(re.escape(name), text, re.I)
        text = (text[:hit.start()] + _mention(name) + text[hit.end():]) if hit else f"{_mention(name)} {text}".strip()
    return text


def render(*, number: int, planned: int | None, genre: str, location: dict | None, time_of_day: str, cast: list[dict], beats: list[dict],
           mood: str, camera: str = "") -> str:
    """cast: [{character_id, name, description, wardrobe}]; beats: [{start,end,size,lens,camera,action,cast:[id],dialogue:[{character_id,text}]}]"""
    names = {c["character_id"]: c["name"] for c in cast}
    total = beats[-1]["end"] if beats else float(planned or 8)
    fmt = [f"{total:g}s", f"{max(len(beats), 1)} SHOT" + ("S" if max(len(beats), 1) > 1 else "")]
    if genre.strip():
        fmt.append(genre.strip())
    lines = [f"ADEGAN {number}" + (f" — #[{location['name']}]" if location else ""), "FORMAT: " + " / ".join(fmt)]
    subject = " ".join(f"{_mention(c['name'])}" + (f", {' '.join((c.get('description') or '').split())[:DESC_CLIP].rstrip('.')}" if c.get("description") else "") + "."
                       for c in cast)
    lines.append("SUBJECT: " + (subject or "(tanpa pemeran)"))
    wardrobe = [f"{c['name']}: {c['wardrobe'].strip().rstrip('.')}." for c in cast if (c.get("wardrobe") or "").strip()]
    if wardrobe:
        lines.append("WARDROBE: " + " ".join(wardrobe))
    if location:
        env = f"#[{location['name']}]" + (f", {time_of_day.strip()}" if time_of_day.strip() else "")
        desc = " ".join((location.get("description") or "").split())[:300].rstrip(".")
        lines.append("ENVIRONMENT: " + env + "." + (f" {desc}." if desc else ""))
    else:
        lines.append("ENVIRONMENT: (tanpa latar)")
    if mood.strip():
        lines.append("MOOD: " + mood.strip())
    if not beats:   # adegan lama tanpa beat: satu shot sepanjang durasi, aksi pemeran dari data lama
        acts = [f"{_mention(c['name'])} {c['action'].strip().rstrip('.')}".strip() for c in cast if c.get("action")]
        beats = [{"start": 0.0, "end": float(planned or 8), "size": None, "lens": None, "camera": camera, "cast": [c["character_id"] for c in cast],
                  "action": "", "dialogue": [], "_text": ". ".join(acts)}]
    for i, b in enumerate(beats, 1):
        tech = [x for x in ((b.get("size") or ""), f"{b['lens']}mm" if b.get("lens") else "", (b.get("camera") or "").strip()) if x]
        head = f"SHOT {i} — {ts(b['start'])} to {ts(b['end'])}" + ("".join(f", {t}" for t in tech))
        who = [names[c] for c in b.get("cast", []) if c in names]
        body = b["_text"] if b.get("_text") else _action_text(b.get("action") or "", who) if (b.get("action") or who) else ""
        say = [f'{_mention(names.get(d["character_id"], "?"))} says: "{d["text"]}"' for d in b.get("dialogue", []) if d["character_id"] in names]
        text = ". ".join(x.rstrip(".") for x in [body, *say] if x)
        lines.append(f"{head}. {text}." if text else f"{head}.")
    return "\n".join(lines)


class ScenePrompt:
    def __init__(self, studio):
        self.st = studio

    # ---------- bahan ----------
    def _pools(self, ws: str) -> tuple[list[dict], list[dict]]:
        db = self.st.db
        return (db.all("SELECT id, name, description FROM characters WHERE workspace_id = ?", (ws,)),
                db.all("SELECT id, name, description, image_id FROM locations WHERE workspace_id = ?", (ws,)))

    def _render_from_data(self, scene: dict, ws: str) -> str:
        st = self.st
        film_cast = st.db.all(
            "SELECT sc.character_id, sc.action, c.name, c.description, o.name AS outfit_name, o.description AS outfit_desc FROM scene_cast sc "
            "JOIN characters c ON c.id = sc.character_id LEFT JOIN outfits o ON o.id = sc.outfit_id WHERE sc.scene_id = ? ORDER BY sc.position", (scene["id"],))
        cast = [{"character_id": r["character_id"], "name": r["name"], "description": r["description"], "action": r["action"],
                 "wardrobe": r["outfit_desc"] or r["outfit_name"] or ""} for r in film_cast]
        loc = st.db.one("SELECT name, description FROM locations WHERE id = ?", (scene["location_id"],)) if scene["location_id"] else None
        beats = st.beats.list(scene["id"], ws)["beats"]
        return render(number=scene["position"] + 1, planned=scene["planned_seconds"], genre=st.workspaces.get(ws)["genre"] or "", location=loc,
                      time_of_day=scene["time_of_day"], cast=cast, beats=beats, mood=scene["extra_prompt"], camera=scene["camera"])

    def text(self, scene: dict, ws: str) -> tuple[str, bool]:
        """(teks prompt, turunan?) — turunan = belum pernah disimpan/basi, dirender dari data."""
        if scene.get("prompt"):
            return scene["prompt"], False
        return self._render_from_data(scene, ws), True

    def _check_names(self, text: str, chars: list[dict], locs: list[dict]) -> None:
        for pool, kind, sign in ((chars, "character", "@"), (locs, "location", "#")):
            count: dict[str, int] = {}
            for p in pool:
                count[script.key(p["name"])] = count.get(script.key(p["name"]), 0) + 1
            for k, name in script.mentions(text):
                if k != kind:
                    continue
                n = count.get(script.key(name), 0)
                if n == 0:
                    raise ServiceError(f"{sign}[{name}] tidak ada di proyek ini; buat dulu di langkah Proyek & pemeran atau perbaiki namanya", 422)
                if n > 1:
                    raise ServiceError(f"{sign}[{name}] bernama ganda di proyek; ganti salah satu namanya", 422)

    def parse(self, text: str, ws: str, scene_number: int = 1) -> dict:
        """Urai satu blok adegan. Galat → ServiceError 422 yang menyebut penyebabnya."""
        text = (text or "").replace("\r\n", "\n").strip()
        if not text:
            raise ServiceError("prompt adegan kosong", 422)
        if len(text) > PROMPT_MAX:
            raise ServiceError(f"prompt adegan maksimal {PROMPT_MAX} karakter", 422)
        chars, locs = self._pools(ws)
        self._check_names(text, chars, locs)
        out = script_format.parse(text, chars, locs)
        if out["errors"]:
            raise ServiceError(re.sub(r"^adegan \d+: ", "", out["errors"][0]), 422, {"errors": out["errors"]})
        if len(out["scenes"]) != 1:
            raise ServiceError("prompt adegan harus berisi tepat satu blok (satu FORMAT dan daftar SHOT)", 422)
        return {"scene": out["scenes"][0], "warnings": [re.sub(r"^adegan \d+: ", "", w) for w in out["warnings"]]}

    # ---------- API ----------
    def _assets(self, scene_id: str, ws: str) -> dict:
        cast, _ = self.st.sbvideo._cast(scene_id, ws)
        scene = self.st.scenes._scene(scene_id, ws)
        loc = self.st.db.one("SELECT id, name, image_id FROM locations WHERE id = ?", (scene["location_id"],)) if scene["location_id"] else None
        return {"characters": [{"id": c["character_id"], "name": c["name"], "image_id": c["image_id"]} for c in cast], "location": loc}

    def get(self, scene_id: str, ws: str = DEFAULT_WS) -> dict:
        scene = self.st.scenes._scene(scene_id, ws)
        text, derived = self.text(scene, ws)
        return {"prompt": text, "derived": derived, "assets": self._assets(scene_id, ws), **self.check(scene_id, text, ws)}

    def check(self, scene_id: str, text: str, ws: str = DEFAULT_WS) -> dict:
        """Validasi tanpa menyimpan: {"errors":[…], "warnings":[…]} + aset yang akan terhubung bila disimpan."""
        self.st.scenes._scene(scene_id, ws)
        try:
            r = self.parse(text, ws)
        except ServiceError as exc:
            return {"errors": [str(exc)], "warnings": [], "will_link": None}
        s = r["scene"]
        chars, locs = self._pools(ws)
        by = {c["id"]: c for c in chars}
        warnings = list(r["warnings"])
        link = {"characters": [{"id": c["character_id"], "name": by[c["character_id"]]["name"]} for c in s["cast"]],
                "location": next(({"id": l["id"], "name": l["name"], "image_id": l["image_id"]} for l in locs if l["id"] == s["location_id"]), None)}
        for c in s["cast"]:
            row = self.st.db.one("SELECT source_image_id FROM characters WHERE id = ?", (c["character_id"],))
            if not row or not row["source_image_id"]:
                warnings.append(f"{by[c['character_id']]['name']} belum punya gambar; dikirim hanya sebagai teks")
        if link["location"] and not link["location"]["image_id"]:
            warnings.append(f"latar {link['location']['name']} belum punya gambar; dikirim hanya sebagai teks")
        return {"errors": [], "warnings": warnings, "will_link": link}

    def put(self, scene_id: str, text: str, ws: str = DEFAULT_WS) -> dict:
        st = self.st
        with st._lock:
            scene = st.scenes._scene(scene_id, ws)
            st.scenes._editable(scene["film_id"])
            s = self.parse(text, ws, scene["position"] + 1)["scene"]   # SEMUA validasi sebelum menulis apa pun
            old = {c["character_id"]: c for c in st.scenes._cast(scene_id)}
            cast = [{"character_id": c["character_id"], "outfit_id": (old.get(c["character_id"]) or {}).get("outfit_id"),
                     "action": (old.get(c["character_id"]) or {}).get("action", "")} for c in s["cast"]]
            st.scenes.update(scene_id, {"location_id": s["location_id"], "cast": cast, "extra_prompt": s["extra_prompt"],
                                        "planned_seconds": s["planned_seconds"]}, ws)
            current = st.beats.list(scene_id, ws)["beats"]
            keys = ("start", "end", "action", "camera", "size", "lens", "cast", "dialogue")
            if [{k: b[k] for k in keys} for b in current] != [{k: b[k] for k in keys} for b in s["beats"]]:
                st.beats.replace(scene_id, s["beats"], "dari prompt adegan", ws)
            st.db.update("scenes", scene_id, {"prompt": text.replace("\r\n", "\n").strip(), "updated_at": now_()})
        return self.get(scene_id, ws)


    # ---------- AI: ubah prompt adegan (plan 18 Revisi 10); draf, tidak disimpan ----------
    SCENE_REVISE_TOKENS = (2000, 6000)

    def _revise_inputs(self, scene_id: str, ws: str, instruction: str) -> tuple[str, str, int, dict]:
        st = self.st
        scene = st.scenes._scene(scene_id, ws)
        film = st.films._row(scene["film_id"], ws)
        project = st.workspaces.get(ws)
        text, _ = self.text(scene, ws)
        chars, locs = self._pools(ws)
        user = script.revise_user(film["title"], film["synopsis"], chars, locs, text, instruction)
        head = "".join(f"{k}: {v}\n" for k, v in (("Genre", project["genre"] or ""), ("Visual style", project["style"])) if v)
        lo, hi = self.SCENE_REVISE_TOKENS
        return script.REVISE_SCENE_SYSTEM, head + user, max(lo, min(hi, int(len(text) / 2.2) + 1500)), scene

    def revise_estimate(self, scene_id: str, ws: str = DEFAULT_WS, model: str | None = None):
        system, user, tokens, _ = self._revise_inputs(scene_id, ws, "x" * script.INSTRUCTION_MAX)   # instruksi konstan → estimasi = panggilan
        return textai.estimate(self.st, system, user, tokens, min_out=min(tokens, 1500), model=model)

    @staticmethod
    def changed_lines(old: str, new: str) -> list[int]:
        """Nomor baris (1-based) di `new` yang tidak ada di `old` (multiset baris ternormalisasi, bukan posisi)."""
        pool: dict[str, int] = {}
        for l in old.splitlines():
            pool[" ".join(l.split())] = pool.get(" ".join(l.split()), 0) + 1
        out = []
        for n, l in enumerate(new.splitlines(), 1):
            k = " ".join(l.split())
            if pool.get(k, 0) > 0:
                pool[k] -= 1
            elif k:
                out.append(n)
        return out

    def revise(self, scene_id: str, instruction: str, ws: str = DEFAULT_WS, confirmed_cost: float | None = None,
               accept_unknown_cost: bool = False, model: str | None = None) -> dict:
        instruction = (instruction or "").strip()
        if not instruction:
            raise ServiceError("tulis dulu apa yang ingin diubah", 422)
        if len(instruction) > script.INSTRUCTION_MAX:
            raise ServiceError(f"instruksi maksimal {script.INSTRUCTION_MAX} karakter", 422)
        st = self.st
        with st._lock:
            system, user, tokens, scene = self._revise_inputs(scene_id, ws, instruction)
            st.scenes._editable(scene["film_id"])
            _, padded, _, _ = self._revise_inputs(scene_id, ws, "x" * script.INSTRUCTION_MAX)
            est = textai.estimate(st, system, padded, tokens, min_out=min(tokens, 1500), model=model)
            previous = self.text(scene, ws)[0]
            total, last_error = 0.0, ""
            for attempt in (1, 2):
                raw, cost = textai.ask(st, "scene_prompt_revise", system, user + (f"\n\nYour previous answer was rejected: {last_error}. Fix it and answer again."
                                                                                  if last_error else ""),
                                       tokens, est, ws, confirmed_cost, accept_unknown_cost, scene_id=scene_id, model=model)
                total += cost or 0.0
                text = raw.get("script") if isinstance(raw.get("script"), str) else ""
                try:
                    if not text.strip():
                        raise ServiceError("jawaban kosong", 422)
                    parsed = self.parse(text, ws, scene["position"] + 1)
                    return {"prompt": text.strip(), "previous": previous, "changed": self.changed_lines(previous, text.strip()),
                            "warnings": parsed["warnings"], "cost": total or None, "estimated_cost": est.high, "attempts": attempt}
                except ServiceError as exc:
                    last_error = str(exc)
            raise ServiceError(f"AI menghasilkan prompt adegan yang tidak sesuai format ({last_error}); coba lagi, perjelas instruksi, atau pilih model lain", 502)


def now_() -> str:
    from .db import now
    return now()
