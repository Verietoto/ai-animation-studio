"""Adegan, latar, dan tampilan/baju karakter untuk storyboard per episode (plan 08).

Episode = baris `films`. Adegan menyimpan naskah terstruktur (latar, pemeran + tampilan + aksi, kamera) dan menunjuk
satu keyframe + satu video terpilih. Modul ini tidak memanggil AI; semuanya gratis. Semua akses dibatasi workspace
lewat film induk (adegan) atau kolom workspace_id (latar) atau karakter induk (tampilan).
"""
import json
import uuid

from . import blockout, layout_solver, media, pricing, sceneprompt, textai
from .db import now
from .films import MAX_SCENES
from .openrouter import OpenRouterError
from .service import DEFAULT_WS, ServiceError

MAX_CAST = 3                       # 1 gambar latar + 3 pemeran = 4 input, muat di batas 5 kebanyakan model
LIMITS = {"time_of_day": 60, "camera": 120, "dialogue": 1000, "extra_prompt": 500}
ACTION_MAX, NAME_MAX, DESC_MAX = 200, 60, 300
SCENE_FIELDS = {*LIMITS, "start_from_prev", "location_id", "keyframe_image_id", "clip_id", "cast", "planned_seconds", "blockout", "blockout_image_id",
                "script_excerpt"}
PREVIS_MODEL = "bytedance/seedance-2.0-mini"   # bawaan "video dari previs": termurah di keluarga Seedance reference
MANNEQUIN_COLORS = ("blue", "orange", "green", "purple")   # urutan warna manekin di blockoutScene.ts
BLOCKOUT_MAX_TOKENS = 6000   # batas keluaran AI penyusun; juga dasar estimasi biaya tertinggi (grill 14)
MAX_PLANNED = 120   # detik; batas wajar satu adegan
INHERITED = ("location_id", "time_of_day")   # adegan baru mewarisi latar, waktu, pemeran + tampilan (aksi dikosongkan)
ACTIVE = ("submitted", "in_progress")


def _text(value, what: str, limit: int, required: bool = False) -> str:
    value = (value or "").strip()
    if required and not value:
        raise ServiceError(f"{what} wajib diisi", 422)
    if len(value) > limit:
        raise ServiceError(f"{what} maksimal {limit} karakter", 422)
    return value


class Scenes:
    def __init__(self, studio):
        self.st = studio

    # ---------- util ----------
    def _scene(self, scene_id: str, ws: str = DEFAULT_WS) -> dict:
        row = self.st.db.one("SELECT s.* FROM scenes s JOIN films f ON f.id = s.film_id "
                             "WHERE s.id = ? AND f.workspace_id = ?", (scene_id, ws))
        if not row:
            raise ServiceError("adegan tidak ditemukan", 404)
        return row

    def _editable(self, film_id: str) -> None:
        film = self.st.db.one("SELECT render_status FROM films WHERE id = ?", (film_id,))
        if film and film["render_status"] == "rendering":
            raise ServiceError("episode sedang dirender; tunggu selesai", 409)

    def _order(self, film_id: str) -> list[str]:
        return [r["id"] for r in self.st.db.all("SELECT id FROM scenes WHERE film_id = ? ORDER BY position", (film_id,))]

    @staticmethod
    def _renumber(tx, ids: list[str]) -> None:
        for pos, sid in enumerate(ids):   # selalu 0..n-1, tidak pernah "position + 1" sebagian
            tx.execute("UPDATE scenes SET position = ? WHERE id = ?", (pos, sid))

    def _cast(self, scene_id: str) -> list[dict]:
        return self.st.db.all(
            "SELECT sc.character_id, sc.outfit_id, sc.action, c.name AS character_name, c.description AS character_description, o.name AS outfit_name, "
            "COALESCE(o.image_id, c.source_image_id) AS image_id FROM scene_cast sc "
            "JOIN characters c ON c.id = sc.character_id LEFT JOIN outfits o ON o.id = sc.outfit_id "
            "WHERE sc.scene_id = ? ORDER BY sc.position", (scene_id,))

    def public(self, s: dict) -> dict:
        db = self.st.db
        loc = db.one("SELECT id, name, image_id FROM locations WHERE id = ?", (s["location_id"],)) if s["location_id"] else None
        clip = db.one("SELECT status FROM clips WHERE id = ? AND deleted_at IS NULL", (s["clip_id"],)) if s["clip_id"] else None
        if clip is None and s["clip_id"]:
            clip = {"status": "missing"}
        if clip and clip["status"] in ACTIVE:
            status = "video_diproses"
        elif clip and clip["status"] == "completed":
            status = "siap"
        elif clip:
            status = "gagal"
        elif s["keyframe_image_id"]:
            status = "keyframe"
        else:
            status = "naskah"
        return {"id": s["id"], "film_id": s["film_id"], "position": s["position"], "number": s["position"] + 1,
                "location": loc, "time_of_day": s["time_of_day"], "camera": s["camera"], "dialogue": s["dialogue"],
                "extra_prompt": s["extra_prompt"], "keyframe_image_id": s["keyframe_image_id"], "clip_id": s["clip_id"],
                "cast": self._cast(s["id"]), "status": status, "clip_status": clip["status"] if clip else None,
                "planned_seconds": s["planned_seconds"], "updated_at": s["updated_at"], "start_from_prev": bool(s["start_from_prev"]),
                "blockout": json.loads(s["blockout"]) if s["blockout"] else None,
                "blockout_image_id": s["blockout_image_id"], "previs_ref_id": s["previs_ref_id"], "script_excerpt": s["script_excerpt"] or "",
                "keyframe_takes": [r["id"] for r in db.all(
                    "SELECT id FROM images WHERE scene_id = ? AND deleted_at IS NULL ORDER BY created_at DESC", (s["id"],))],
                "video_takes": db.all("SELECT id, status FROM clips WHERE scene_id = ? AND deleted_at IS NULL "
                                      "ORDER BY created_at DESC", (s["id"],))}

    def list_for(self, film_id: str) -> list[dict]:
        return [self.public(r) for r in self.st.db.all("SELECT * FROM scenes WHERE film_id = ? ORDER BY position", (film_id,))]

    def get(self, scene_id: str, ws: str = DEFAULT_WS) -> dict:
        return self.public(self._scene(scene_id, ws))

    # ---------- validasi rujukan ----------
    def _location(self, location_id: str, ws: str) -> dict:
        row = self.st.db.one("SELECT * FROM locations WHERE id = ? AND workspace_id = ?", (location_id, ws))
        if not row:
            raise ServiceError("latar tidak ditemukan", 404)
        return row

    def _check_cast(self, cast: list[dict], ws: str) -> list[dict]:
        if len(cast) > MAX_CAST:
            raise ServiceError(f"maksimum {MAX_CAST} pemeran per adegan", 422)
        seen, clean = set(), []
        for item in cast:
            cid = item.get("character_id")
            if cid in seen:
                raise ServiceError("karakter yang sama tidak boleh dua kali di satu adegan", 422)
            seen.add(cid)
            self.st.get_character(cid, ws)   # 404 lintas workspace
            outfit_id = item.get("outfit_id") or None
            if outfit_id and not self.st.db.one("SELECT 1 FROM outfits WHERE id = ? AND character_id = ?", (outfit_id, cid)):
                raise ServiceError("tampilan bukan milik karakter itu", 422)
            clean.append({"character_id": cid, "outfit_id": outfit_id, "action": _text(item.get("action"), "aksi", ACTION_MAX)})
        return clean

    # ---------- adegan ----------
    def add(self, film_id: str, ws: str = DEFAULT_WS, after_scene_id: str | None = None, inherit: bool = True,
            clip_id: str | None = None) -> dict:
        with self.st._lock:
            self.st.films._row(film_id, ws)
            self._editable(film_id)
            order = self._order(film_id)
            if len(order) >= MAX_SCENES:
                raise ServiceError(f"maksimum {MAX_SCENES} adegan", 422)
            if after_scene_id:
                if after_scene_id not in order:
                    raise ServiceError("adegan acuan tidak ada di episode ini", 404)
                index = order.index(after_scene_id) + 1
            else:
                index = len(order)
            prev = self._scene(order[index - 1], ws) if index > 0 else None
            row = {"id": uuid.uuid4().hex, "film_id": film_id, "position": index, "created_at": now(), "updated_at": now()}
            cast: list[dict] = []
            if clip_id:
                clip = self.st.get_clip(clip_id, ws)
                row["clip_id"] = clip_id
                alive = clip["source_image_id"] and self.st.db.one(
                    "SELECT 1 FROM images WHERE id = ? AND deleted_at IS NULL AND workspace_id = ?", (clip["source_image_id"], ws))
                row["keyframe_image_id"] = clip["source_image_id"] if alive else None
            elif inherit and prev:
                row.update({k: prev[k] for k in INHERITED})
                cast = [{"character_id": c["character_id"], "outfit_id": c["outfit_id"], "action": ""} for c in self._cast(prev["id"])]
            order.insert(index, row["id"])
            with self.st.db.transaction() as tx:
                tx.insert("scenes", row)
                for pos, c in enumerate(cast):
                    tx.insert("scene_cast", {"scene_id": row["id"], **c, "position": pos})
                self._renumber(tx, order)
                tx.execute("UPDATE films SET updated_at = ? WHERE id = ?", (now(), film_id))
        return self.get(row["id"], ws)

    def update(self, scene_id: str, fields: dict, ws: str = DEFAULT_WS) -> dict:
        unknown = set(fields) - SCENE_FIELDS
        if unknown:
            raise ServiceError(f"field tidak dikenal: {sorted(unknown)[0]}", 422)
        with self.st._lock:
            scene = self._scene(scene_id, ws)
            values: dict = {}
            for key, limit in LIMITS.items():
                if key in fields:
                    values[key] = _text(fields[key], key, limit)
            if "location_id" in fields:
                lid = fields["location_id"] or None
                if lid:
                    self._location(lid, ws)
                values["location_id"] = lid
            if "keyframe_image_id" in fields or "clip_id" in fields:
                self._editable(scene["film_id"])   # memilih take mengubah hasil render
            if "keyframe_image_id" in fields:
                iid = fields["keyframe_image_id"] or None
                if iid:
                    self.st.get_image(iid, ws)
                values["keyframe_image_id"] = iid
            if "clip_id" in fields:
                cid = fields["clip_id"] or None
                if cid:
                    self.st.get_clip(cid, ws)
                values["clip_id"] = cid
            if "start_from_prev" in fields:
                flag = fields["start_from_prev"]
                if not isinstance(flag, bool):
                    raise ServiceError("start_from_prev harus true atau false", 422)
                if flag and scene["position"] == 0:
                    raise ServiceError("adegan pertama tidak punya adegan sebelumnya", 422)
                values["start_from_prev"] = 1 if flag else 0
            if "planned_seconds" in fields:
                secs = fields["planned_seconds"]
                if secs is not None and (isinstance(secs, bool) or not isinstance(secs, int) or not 1 <= secs <= MAX_PLANNED):
                    raise ServiceError(f"durasi rencana 1 sampai {MAX_PLANNED} detik", 422)
                values["planned_seconds"] = secs
            cast = self._check_cast(fields["cast"] or [], ws) if "cast" in fields else None
            if "script_excerpt" in fields:
                values["script_excerpt"] = _text(fields["script_excerpt"], "potongan naskah", 500)
            if "blockout" in fields:   # aktor harus pemeran adegan (pemeran baru bila ikut diubah di panggilan yang sama)
                cast_ids = [c["character_id"] for c in (cast if cast is not None else self._cast(scene_id))]
                raw = fields["blockout"]
                set_ids = [o["id"] for o in self._set_layout(values.get("location_id", scene["location_id"])).get("objects", [])]
                values["blockout"] = json.dumps(blockout.clean(raw, cast_ids, set_ids)) if raw else None
            if "blockout_image_id" in fields:
                iid = fields["blockout_image_id"] or None
                if iid:
                    self.st.get_image(iid, ws)
                values["blockout_image_id"] = iid
            if {"location_id", "planned_seconds", "extra_prompt", "cast"} & set(fields):
                values["prompt"] = None   # prompt adegan dirender ulang dari data (plan 18 Revisi 8); put_prompt menulisnya lagi sesudahnya
            values["updated_at"] = now()
            with self.st.db.transaction() as tx:
                sets = ", ".join(f"{k} = ?" for k in values)
                tx.execute(f"UPDATE scenes SET {sets} WHERE id = ?", (*values.values(), scene_id))
                if cast is not None:
                    tx.execute("DELETE FROM scene_cast WHERE scene_id = ?", (scene_id,))
                    for pos, c in enumerate(cast):
                        tx.insert("scene_cast", {"scene_id": scene_id, **c, "position": pos})
            # plan 15: pemeran/latar yang dipakai adegan otomatis menjadi bagian episode (alur lama lewat Mode lanjutan tetap jalan)
            self.st.journey.ensure(scene["film_id"], [c["character_id"] for c in cast or []], values.get("location_id"))
        return self.get(scene_id, ws)

    def delete(self, scene_id: str, ws: str = DEFAULT_WS) -> None:
        with self.st._lock:
            scene = self._scene(scene_id, ws)
            self._editable(scene["film_id"])
            order = [i for i in self._order(scene["film_id"]) if i != scene_id]
            with self.st.db.transaction() as tx:
                for table in ("images", "clips"):   # hasil generate tetap di library, hanya lepas dari adegan
                    tx.execute(f"UPDATE {table} SET scene_id = NULL WHERE scene_id = ?", (scene_id,))
                tx.execute("DELETE FROM scene_cast WHERE scene_id = ?", (scene_id,))
                tx.execute("DELETE FROM scene_beats WHERE scene_id = ?", (scene_id,))
                tx.execute("DELETE FROM beat_versions WHERE scene_id = ?", (scene_id,))
                tx.execute("DELETE FROM scenes WHERE id = ?", (scene_id,))
                self._renumber(tx, order)

    def delete_many(self, film_id: str, scene_ids: list[str], ws: str = DEFAULT_WS) -> dict:
        """Hapus banyak adegan satu episode dalam SATU transaksi (semua atau tidak sama sekali), lalu nomori ulang sekali.
        Hasil generate tetap di library; hanya terlepas dari adegan (sama seperti delete satuan)."""
        ids = list(dict.fromkeys(scene_ids))
        if not ids:
            raise ServiceError("pilih minimal satu adegan", 422)
        with self.st._lock:
            film = self.st.films._row(film_id, ws)   # 404 bila episode milik workspace lain
            self._editable(film_id)
            order = self._order(film_id)
            missing = [i for i in ids if i not in order]
            if missing:
                raise ServiceError("ada adegan yang bukan bagian episode ini", 404)
            keep = [i for i in order if i not in set(ids)]
            marks = ", ".join("?" for _ in ids)
            with self.st.db.transaction() as tx:
                for table in ("images", "clips"):
                    tx.execute(f"UPDATE {table} SET scene_id = NULL WHERE scene_id IN ({marks})", tuple(ids))
                for table in ("scene_cast", "scene_beats", "beat_versions"):
                    tx.execute(f"DELETE FROM {table} WHERE scene_id IN ({marks})", tuple(ids))
                tx.execute(f"DELETE FROM scenes WHERE id IN ({marks})", tuple(ids))
                self._renumber(tx, keep)
        return {"deleted": len(ids), "remaining": len(keep), "film_id": film["id"]}

    def duplicate(self, scene_id: str, ws: str = DEFAULT_WS) -> dict:
        """Salin naskahnya saja (latar, waktu, kamera, dialog, teks tambahan, pemeran). Keyframe/video tidak ikut: salinan perlu take sendiri."""
        with self.st._lock:
            scene = self._scene(scene_id, ws)
            new = self.add(scene["film_id"], ws, after_scene_id=scene_id, inherit=False)
            self.update(new["id"], {"location_id": scene["location_id"], "time_of_day": scene["time_of_day"],
                                    "camera": scene["camera"], "dialogue": scene["dialogue"], "extra_prompt": scene["extra_prompt"],
                                    "planned_seconds": scene["planned_seconds"],
                                    "blockout": json.loads(scene["blockout"]) if scene["blockout"] else None,
                                    "cast": [{k: c[k] for k in ("character_id", "outfit_id", "action")} for c in self._cast(scene_id)]}, ws)
        return self.get(new["id"], ws)

    # ---------- blockout 3D + previs (plan 14) ----------
    def _set_layout(self, location_id: str | None) -> dict:
        """Set latar (plan 17): {version, bounds, environment, objects:[prop]}; kosong bila belum dibuat."""
        row = self.st.db.one("SELECT set_layout FROM locations WHERE id = ?", (location_id,)) if location_id else None
        return json.loads(row["set_layout"]) if row and row["set_layout"] else {}

    def _blockout_context(self, scene_id: str, ws: str) -> dict:
        scene = self._scene(scene_id, ws)
        film = self.st.films._row(scene["film_id"], ws)
        loc = self.st.db.one("SELECT name, description FROM locations WHERE id = ?", (scene["location_id"],)) if scene["location_id"] else None
        secs = scene["planned_seconds"] or blockout.DEFAULT_DURATION
        return {"scene": scene, "duration": max(1, min(blockout.MAX_DURATION, secs)), "ratio": film["aspect_ratio"],
                "location": loc, "time_of_day": scene["time_of_day"], "camera": scene["camera"], "dialogue": scene["dialogue"],
                "extra": scene["extra_prompt"], "set_objects": self._set_layout(scene["location_id"]).get("objects", []),
                "cast": [{"character_id": c["character_id"], "name": c["character_name"], "description": c["character_description"],
                          "action": c["action"]} for c in self._cast(scene_id)]}

    def blockout_estimate(self, scene_id: str, ws: str = DEFAULT_WS, model: str | None = None) -> pricing.Estimate:
        ctx = self._blockout_context(scene_id, ws)
        return textai.estimate(self.st, blockout.SYSTEM, blockout.user_prompt(ctx), BLOCKOUT_MAX_TOKENS, model=model)

    def generate_blockout(self, scene_id: str, ws: str = DEFAULT_WS, confirmed_cost: float | None = None,
                          accept_unknown_cost: bool = False, model: str | None = None) -> dict:
        """AI menyusun blockout. Hasil berupa DRAF (tidak disimpan ke adegan); biaya tercatat di text_jobs."""
        with self.st._lock:
            ctx = self._blockout_context(scene_id, ws)
            self._editable(ctx["scene"]["film_id"])
            est = textai.estimate(self.st, blockout.SYSTEM, blockout.user_prompt(ctx), BLOCKOUT_MAX_TOKENS, model=model)
            raw, cost = textai.ask(self.st, "blockout", blockout.SYSTEM, blockout.user_prompt(ctx), BLOCKOUT_MAX_TOKENS, est, ws,
                                   confirmed_cost, accept_unknown_cost, scene_id=scene_id, model=model)
            cast_ids = [c["character_id"] for c in ctx["cast"]]
            seen: set[str] = set()   # aktor di luar pemeran / ganda dibuang, bukan menggagalkan seluruh susunan
            raw["actors"] = [a for a in raw.get("actors") or [] if isinstance(a, dict) and a.get("character_id") in cast_ids
                             and not (a["character_id"] in seen or seen.add(a["character_id"]))]
            raw["duration"] = ctx["duration"]
            try:
                layout, warnings = blockout.clean_report(raw, cast_ids, [o["id"] for o in ctx["set_objects"]])
            except ServiceError as exc:
                raise ServiceError(f"AI menghasilkan susunan yang tidak valid ({exc}); coba lagi", 502) from exc
        return {"layout": layout, "warnings": warnings, "cost": cost, "estimated_cost": est.high}

    ENV_WORDS = (("pagi", "pagi"), ("fajar", "pagi"), ("siang", "siang"), ("sore", "senja"), ("senja", "senja"), ("malam", "malam"), ("gelap", "malam"))

    def blockout_resolve(self, scene_id: str, ws: str = DEFAULT_WS, layout_raw: dict | None = None) -> dict:
        """Susunan siap render: validasi, gabung set latar + properti adegan, hitung koordinat (pemecah tata letak), pastikan aktor di bingkai."""
        scene = self._scene(scene_id, ws)
        raw = layout_raw if layout_raw is not None else (json.loads(scene["blockout"]) if scene["blockout"] else None)
        if raw is None:
            raise ServiceError("belum ada susunan 3D untuk adegan ini", 404)
        film = self.st.films._row(scene["film_id"], ws)
        cast_ids = [c["character_id"] for c in self._cast(scene_id)]
        sset = self._set_layout(scene["location_id"])
        set_objs = list(sset.get("objects", []))
        layout, warnings = blockout.clean_report(raw, cast_ids, [o["id"] for o in set_objs])
        own = {p["id"] for p in layout["props"]}
        clash = [o["id"] for o in set_objs if o["id"] in own]
        if clash:
            warnings.append(f"id objek set dipakai ulang oleh properti adegan, objek set diabaikan: {', '.join(clash)}")
            set_objs = [o for o in set_objs if o["id"] not in own]
        actor_xz = [(a["keys"][0]["pos"][0], a["keys"][0]["pos"][2]) for a in layout["actors"]]
        bounds = tuple(sset.get("bounds") or layout_solver.DEFAULT_BOUNDS)
        props, solved_warnings = layout_solver.solve(set_objs, layout["props"], actor_xz, bounds)
        w, h = (film["aspect_ratio"].split(":") + ["9"])[:2]
        aspect = float(w) / float(h) if float(h) else 16 / 9
        keys, frame_warnings = layout_solver.frame_actors(layout["camera"]["keys"], actor_xz, aspect)
        text = (scene["time_of_day"] or "").lower()
        env = {"time": next((t for word, t in self.ENV_WORDS if word in text), "siang"), "weather": "cerah",
               **(sset.get("environment") or {}), **layout["environment"]}
        looks = {r["id"]: json.loads(r["look"]) for r in self.st.db.all(
            f"SELECT id, look FROM characters WHERE look IS NOT NULL AND id IN ({','.join('?' * len(cast_ids)) or 'NULL'})", tuple(cast_ids))}
        return {"layout": {**layout, "camera": {"keys": keys}}, "props": props, "environment": env, "bounds": list(bounds), "looks": looks,
                "warnings": [*warnings, *solved_warnings, *frame_warnings]}

    def attach_previs(self, scene_id: str, ref: dict, ws: str = DEFAULT_WS) -> dict:
        """Pasang video previs (baris refs baru) ke adegan; previs lama dihapus bila tidak dipakai klip mana pun."""
        with self.st._lock:
            scene = self._scene(scene_id, ws)
            old = scene["previs_ref_id"]
            self.st.db.update("scenes", scene_id, {"previs_ref_id": ref["id"], "updated_at": now()})
            if old and old != ref["id"] and not self.st.db.one("SELECT 1 FROM clips WHERE reference_id = ?", (old,)):
                row = self.st.db.one("SELECT path FROM refs WHERE id = ?", (old,))
                if row:
                    self.st._unlink(row["path"])
                    self.st.db.execute("DELETE FROM refs WHERE id = ?", (old,))
        return self.get(scene_id, ws)

    def reorder(self, film_id: str, scene_ids: list[str], ws: str = DEFAULT_WS) -> list[dict]:
        with self.st._lock:
            self.st.films._row(film_id, ws)
            self._editable(film_id)
            if sorted(scene_ids) != sorted(self._order(film_id)):
                raise ServiceError("daftar adegan sudah berubah; muat ulang episode", 409)
            with self.st.db.transaction() as tx:
                self._renumber(tx, scene_ids)
                tx.execute("UPDATE films SET updated_at = ? WHERE id = ?", (now(), film_id))
        return self.list_for(film_id)

    # ---------- latar ----------
    def list_locations(self, ws: str = DEFAULT_WS) -> list[dict]:
        return self.st.db.all("SELECT l.*, (SELECT COUNT(*) FROM scenes s WHERE s.location_id = l.id) AS used "
                              "FROM locations l WHERE l.workspace_id = ? ORDER BY l.name COLLATE NOCASE", (ws,))

    def _loc_values(self, name, description, image_id, ws: str, partial: bool = False) -> dict:
        values: dict = {}
        if name is not None or not partial:
            values["name"] = _text(name, "nama latar", NAME_MAX, required=True)
            if "[" in values["name"] or "]" in values["name"]:
                raise ServiceError("nama latar tidak boleh memuat [ atau ]", 422)
        if description is not None:
            values["description"] = _text(description, "deskripsi latar", DESC_MAX)
        if image_id is not None:
            if image_id:
                self.st.get_image(image_id, ws)
            values["image_id"] = image_id or None
        return values

    def create_location(self, name: str, description: str = "", image_id: str | None = None, ws: str = DEFAULT_WS) -> dict:
        row = {"id": uuid.uuid4().hex, "workspace_id": ws, "created_at": now(), "updated_at": now(),
               "description": "", "image_id": None, **self._loc_values(name, description, image_id, ws)}
        self.st.db.insert("locations", row)
        return {**row, "used": 0}

    def update_location(self, location_id: str, fields: dict, ws: str = DEFAULT_WS) -> dict:
        old = self._location(location_id, ws)
        values = self._loc_values(fields.get("name"), fields.get("description"),
                                  fields["image_id"] if "image_id" in fields else None, ws, partial=True)
        if values:
            with self.st._lock:
                self.st.db.update("locations", location_id, {**values, "updated_at": now()})
                if "name" in values and values["name"] != old["name"]:   # plan 15: mention #[nama lama] di naskah ikut diganti
                    self.st.journey.rename_location(location_id, old["name"], values["name"])
        return next(l for l in self.list_locations(ws) if l["id"] == location_id)

    def delete_location(self, location_id: str, ws: str = DEFAULT_WS) -> None:
        with self.st._lock:
            self._location(location_id, ws)
            with self.st.db.transaction() as tx:   # adegan tetap ada, hanya kehilangan latar; gambar tetap di library
                tx.execute("UPDATE scenes SET location_id = NULL, prompt = NULL WHERE location_id = ?", (location_id,))
                tx.execute("DELETE FROM film_locations WHERE location_id = ?", (location_id,))
                tx.execute("DELETE FROM locations WHERE id = ?", (location_id,))

    # ---------- tampilan / baju ----------
    def _outfit(self, outfit_id: str, ws: str) -> dict:
        row = self.st.db.one("SELECT o.* FROM outfits o JOIN characters c ON c.id = o.character_id "
                             "WHERE o.id = ? AND c.workspace_id = ?", (outfit_id, ws))
        if not row:
            raise ServiceError("tampilan tidak ditemukan", 404)
        return row

    def list_outfits(self, character_id: str, ws: str = DEFAULT_WS) -> list[dict]:
        self.st.get_character(character_id, ws)
        return self.st.db.all("SELECT * FROM outfits WHERE character_id = ? ORDER BY created_at, rowid", (character_id,))

    def create_outfit(self, character_id: str, name: str, description: str = "", image_id: str | None = None,
                      ws: str = DEFAULT_WS) -> dict:
        self.st.get_character(character_id, ws)
        row = {"id": uuid.uuid4().hex, "character_id": character_id, "name": _text(name, "nama tampilan", NAME_MAX, required=True),
               "description": _text(description, "deskripsi tampilan", DESC_MAX), "image_id": image_id or None, "created_at": now()}
        if row["image_id"]:
            self.st.get_image(row["image_id"], ws)
        if not row["image_id"] and not row["description"]:
            raise ServiceError("tampilan butuh gambar atau deskripsi", 422)
        self.st.db.insert("outfits", row)
        return row

    def update_outfit(self, outfit_id: str, fields: dict, ws: str = DEFAULT_WS) -> dict:
        row = self._outfit(outfit_id, ws)
        values: dict = {}
        if fields.get("name") is not None:
            values["name"] = _text(fields["name"], "nama tampilan", NAME_MAX, required=True)
        if fields.get("description") is not None:
            values["description"] = _text(fields["description"], "deskripsi tampilan", DESC_MAX)
        if "image_id" in fields:
            if fields["image_id"]:
                self.st.get_image(fields["image_id"], ws)
            values["image_id"] = fields["image_id"] or None
        merged = {**row, **values}
        if not merged["image_id"] and not merged["description"]:
            raise ServiceError("tampilan butuh gambar atau deskripsi", 422)
        if values:
            self.st.db.update("outfits", outfit_id, values)
        return self._outfit(outfit_id, ws)

    def delete_outfit(self, outfit_id: str, ws: str = DEFAULT_WS) -> None:
        with self.st._lock:
            self._outfit(outfit_id, ws)
            with self.st.db.transaction() as tx:
                tx.execute("UPDATE scene_cast SET outfit_id = NULL WHERE outfit_id = ?", (outfit_id,))
                tx.execute("DELETE FROM outfits WHERE id = ?", (outfit_id,))


    # ---------- generate (berbayar; plan 08) ----------
    def _cast_context(self, scene_id: str, ws: str) -> list[dict]:
        out = []
        for c in self.st.db.all("SELECT * FROM scene_cast WHERE scene_id = ? ORDER BY position", (scene_id,)):
            ch = self.st.get_character(c["character_id"], ws)
            outfit = self.st.db.one("SELECT * FROM outfits WHERE id = ?", (c["outfit_id"],)) if c["outfit_id"] else None
            image_id = (outfit or {}).get("image_id") or ch["source_image_id"]
            try:
                self.st.get_image(image_id, ws)
            except ServiceError as exc:
                raise ServiceError(f"gambar karakter \"{ch['name']}\" sudah dihapus", 422) from exc
            text = outfit["description"] if outfit and not outfit["image_id"] else None   # tampilan hanya-teks
            out.append({"name": ch["name"], "description": ch["description"], "action": c["action"],
                        "outfit_text": text, "image_id": image_id})
        return out

    def _aspect_option(self, model: str, ratio: str) -> dict:
        """Kirim rasio episode bila model mendukungnya (Seedream default 1:1 bila tidak dikirim, spike plan 08)."""
        info = next((m for m in self.st.image_models() if m.get("id") == model), None)
        desc = ((info or {}).get("supported_parameters") or {}).get("aspect_ratio") or {}
        return {"aspect_ratio": ratio} if ratio in desc.get("values", []) else {}

    def keyframe_plan(self, scene_id: str, model: str, ws: str = DEFAULT_WS) -> dict:
        """Satu sumber kebenaran daftar gambar input + prompt keyframe; dipakai /api/estimate dan keyframe()."""
        scene = self._scene(scene_id, ws)
        film = self.st.films._row(scene["film_id"], ws)
        if not scene["location_id"]:
            raise ServiceError("pilih latar adegan dulu", 422)
        loc = self._location(scene["location_id"], ws)
        if not loc["image_id"]:
            raise ServiceError(f"latar \"{loc['name']}\" belum punya gambar; pasang gambar atau buat dari deskripsi", 422)
        self.st.get_image(loc["image_id"], ws)
        cast = self._cast_context(scene_id, ws)
        inputs = [loc["image_id"], *[c["image_id"] for c in cast]]
        options = self._aspect_option(model, film["aspect_ratio"])
        self.st._validate_image_params(model, options, len(inputs))
        prompt = sceneprompt.keyframe_prompt(scene, loc, cast)
        if len(prompt) > 4000:
            raise ServiceError("prompt adegan terlalu panjang; ringkas aksi atau teks tambahan", 422)
        return {"scene": scene, "film": film, "inputs": inputs, "prompt": prompt, "options": options}

    def keyframe(self, scene_id: str, model: str, ws: str = DEFAULT_WS, confirmed_cost: float | None = None,
                 accept_unknown_cost: bool = False) -> dict:
        with self.st._lock:
            plan = self.keyframe_plan(scene_id, model, ws)
            self._editable(plan["film"]["id"])
            est = self.st.estimate_image_job(model, n_inputs=len(plan["inputs"]))
            self.st.authorize(est, confirmed_cost, accept_unknown_cost)
            urls = [media.to_data_url(self.st.storage.resolve(self.st.get_image(i, ws)["path"]).read_bytes()) for i in plan["inputs"][1:]]
            made = self.st._run_edit(plan["inputs"][0], plan["prompt"], model, [], plan["options"], est, kind="keyframe",
                                     extra_urls=urls, ws=ws, scene_id=scene_id)
            fresh = self._scene(scene_id, ws)
            if not fresh["keyframe_image_id"]:   # hasil baru dipilih otomatis hanya bila adegan belum punya keyframe
                self.st.db.update("scenes", scene_id, {"keyframe_image_id": made[0]["id"], "updated_at": now()})
        return self.get(scene_id, ws)

    def video_aspect(self, film_ratio: str, model: str, requested: str | None) -> str | None:
        if requested:
            return requested
        info = next((m for m in self.st.video_models() if m.get("id") == model), None)
        return film_ratio if film_ratio in ((info or {}).get("supported_aspect_ratios") or []) else None

    def video_plan(self, scene_id: str, ws: str = DEFAULT_WS) -> dict:
        scene = self._scene(scene_id, ws)
        film = self.st.films._row(scene["film_id"], ws)
        if not scene["keyframe_image_id"]:
            raise ServiceError("buat atau pilih keyframe adegan dulu", 422)
        self.st.get_image(scene["keyframe_image_id"], ws)
        cast = [{"name": c["character_name"], "action": c["action"]} for c in self._cast(scene_id)]
        prompt = sceneprompt.video_prompt(scene, cast)
        if len(prompt) > 4000:
            raise ServiceError("prompt adegan terlalu panjang; ringkas aksi atau teks tambahan", 422)
        return {"scene": scene, "film": film, "image_id": scene["keyframe_image_id"], "prompt": prompt}

    def video(self, scene_id: str, model: str, ws: str = DEFAULT_WS, duration: int | None = None, resolution: str | None = None,
              aspect_ratio: str | None = None, generate_audio: bool = False, idempotency_key: str | None = None,
              confirmed_cost: float | None = None, accept_unknown_cost: bool = False) -> dict:
        with self.st._lock:
            plan = self.video_plan(scene_id, ws)
            self._editable(plan["film"]["id"])
            clip = self.st.create_clip(image_id=plan["image_id"], prompt=plan["prompt"], model=model, duration=duration,
                                       resolution=resolution, aspect_ratio=self.video_aspect(plan["film"]["aspect_ratio"], model, aspect_ratio),
                                       generate_audio=generate_audio, idempotency_key=idempotency_key, confirmed_cost=confirmed_cost,
                                       accept_unknown_cost=accept_unknown_cost, ws=ws, scene_id=scene_id)
            current = self.st.db.one("SELECT status FROM clips WHERE id = ? AND deleted_at IS NULL", (plan["scene"]["clip_id"],)) \
                if plan["scene"]["clip_id"] else None
            if current is None or current["status"] in ("failed", "failed_download"):   # jangan menimpa video bagus dengan job yang belum tentu jadi
                self.st.db.update("scenes", scene_id, {"clip_id": clip["id"], "updated_at": now()})
        return self.get(scene_id, ws)

    def previs_video_plan(self, scene_id: str, ws: str = DEFAULT_WS) -> dict:
        """Video dari previs (Seedance reference): video previs + gambar pemeran/latar. Satu sumber untuk estimasi dan pembuatan."""
        scene = self._scene(scene_id, ws)
        film = self.st.films._row(scene["film_id"], ws)
        if not scene["previs_ref_id"]:
            raise ServiceError("render previs 3D adegan ini dulu", 422)
        ref = self.st.motion.get_ref(scene["previs_ref_id"], ws)
        cast = self._cast_context(scene_id, ws)
        loc = self.st.db.one("SELECT name, image_id FROM locations WHERE id = ?", (scene["location_id"],)) if scene["location_id"] else None
        entries = [(f"CHARACTER {c['name']}", c["image_id"], c["name"]) for c in cast]
        if loc and loc["image_id"]:
            self.st.get_image(loc["image_id"], ws)
            entries.append((f"the LOCATION {loc['name']}", loc["image_id"], None))
        kept, dropped = entries[:3], len(entries) - 3   # Seedance reference menerima maks 3 gambar di aplikasi ini
        if not kept:
            raise ServiceError("adegan butuh minimal satu pemeran atau latar bergambar", 422)
        layout = json.loads(scene["blockout"]) if scene["blockout"] else {}
        order = [a["character_id"] for a in layout.get("actors", [])] or [c["character_id"] for c in self._cast(scene_id)]
        colors = {cid: MANNEQUIN_COLORS[i % len(MANNEQUIN_COLORS)] for i, cid in enumerate(order)}   # sama dengan warna di editor 3D
        by_name = {c["character_name"]: colors.get(c["character_id"]) for c in self._cast(scene_id)}
        roles = [f"Image {n} shows {label}" + (f" (the {by_name[name]} mannequin)" if name and by_name.get(name) else "") + "."
                 for n, (label, _, name) in enumerate(kept, 1)]
        base = sceneprompt.video_prompt(scene, [{"name": c["name"], "action": c["action"]} for c in cast])
        prompt = (f"{base}\n---\nVideo 1 is a rough 3D previs made with plain mannequins: copy its camera movement, framing, timing and each "
                  "mannequin's movement exactly, but do NOT copy the mannequin look. " + " ".join(roles) +
                  " Replace each mannequin with its character and use the location as the setting.")
        if len(prompt) > 4000:
            raise ServiceError("prompt adegan terlalu panjang; ringkas aksi atau teks tambahan", 422)
        return {"scene": scene, "film": film, "ref_id": ref["id"], "ref_seconds": ref["duration"], "image_ids": [e[1] for e in kept],
                "prompt": prompt, "dropped_images": max(dropped, 0)}

    def previs_video(self, scene_id: str, model: str, ws: str = DEFAULT_WS, duration: int | None = None, resolution: str | None = None,
                     aspect_ratio: str | None = None, generate_audio: bool = False, idempotency_key: str | None = None,
                     confirmed_cost: float | None = None, accept_unknown_cost: bool = False) -> dict:
        plan = self.previs_video_plan(scene_id, ws)
        self._editable(plan["film"]["id"])
        clip = self.st.motion.create(mode="reference", model=model, ref_id=plan["ref_id"], prompt=plan["prompt"], image_ids=plan["image_ids"],
                                     duration=duration, resolution=resolution,
                                     aspect_ratio=self.video_aspect(plan["film"]["aspect_ratio"], model, aspect_ratio),
                                     generate_audio=generate_audio, idempotency_key=idempotency_key, confirmed_cost=confirmed_cost,
                                     accept_unknown_cost=accept_unknown_cost, ws=ws, scene_id=scene_id)
        with self.st._lock:
            cur = self.st.db.one("SELECT status FROM clips WHERE id = ? AND deleted_at IS NULL", (plan["scene"]["clip_id"],)) \
                if plan["scene"]["clip_id"] else None
            if cur is None or cur["status"] in ("failed", "failed_download"):
                self.st.db.update("scenes", scene_id, {"clip_id": clip["id"], "updated_at": now()})
        return self.get(scene_id, ws)

    def location_plan(self, location_id: str, model: str, ws: str = DEFAULT_WS) -> dict:
        loc = self._location(location_id, ws)
        options = self._aspect_option(model, "16:9")
        self.st._validate_image_params(model, options, 0)
        return {"location": loc, "options": options, "prompt": sceneprompt.location_prompt(loc["name"], loc["description"])}

    def location_image(self, location_id: str, model: str, ws: str = DEFAULT_WS, confirmed_cost: float | None = None,
                       accept_unknown_cost: bool = False) -> dict:
        """Buat gambar latar dari deskripsi (teks ke gambar, tanpa gambar input) dan pasang ke latar itu."""
        with self.st._lock:
            plan = self.location_plan(location_id, model, ws)
            est = self.st.estimate_image_job(model, n_inputs=0)
            self.st.authorize(est, confirmed_cost, accept_unknown_cost)
            try:
                resp = self.st.client.generate_image(model, plan["prompt"], **plan["options"])
            except OpenRouterError as exc:
                raise ServiceError(str(exc), 502) from exc
            img = self.st._store_edit_results(resp, None, plan["prompt"], model, est, "location", ws)[0]
            self.st.db.update("locations", location_id, {"image_id": img["id"], "updated_at": now()})
        return next(l for l in self.list_locations(ws) if l["id"] == location_id)
