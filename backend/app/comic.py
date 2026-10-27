"""Panel komik (plan 21): satu panel = gambar AI (latar + karakter proyek sebagai referensi) + balon teks overlay yang diedit di UI.

Referensi basi (karakter/latar/gambar dihapus) dibersihkan saat dibaca, bukan di setiap jalur hapus."""
import json
import uuid

from . import comic_prompt, media
from .db import now
from .openrouter import OpenRouterError
from .service import DEFAULT_WS, ServiceError

RATIOS = ("4:3", "3:4", "1:1", "16:9", "9:16", "3:2", "2:3")
KINDS = ("speech", "thought", "caption", "sfx")
MAX_CAST, MAX_BUBBLES, TEXT_MAX, TITLE_MAX, DESC_MAX = 4, 20, 300, 120, 2000


class Comic:
    def __init__(self, studio):
        self.st = studio

    def _row(self, panel_id: str, ws: str) -> dict:
        row = self.st.db.one("SELECT * FROM comic_panels WHERE id = ? AND workspace_id = ?", (panel_id, ws))
        if not row:
            raise ServiceError("panel tidak ditemukan", 404)
        return row

    def _takes(self, panel_id: str) -> list[str]:
        return [r["id"] for r in self.st.db.all("SELECT id FROM images WHERE panel_id = ? AND deleted_at IS NULL ORDER BY created_at", (panel_id,))]

    def public(self, row: dict, ws: str) -> dict:
        db = self.st.db
        ids = json.loads(row["character_ids"])
        alive = {r["id"] for r in db.all(f"SELECT id FROM characters WHERE workspace_id = ? AND id IN ({','.join('?' * len(ids))})",
                                         (ws, *ids))} if ids else set()
        loc = db.one("SELECT id FROM locations WHERE id = ? AND workspace_id = ?", (row["location_id"], ws)) if row["location_id"] else None
        takes = self._takes(row["id"])
        image = row["image_id"] if row["image_id"] in takes else (takes[-1] if takes else None)
        return {"id": row["id"], "title": row["title"], "description": row["description"],
                "character_ids": [c for c in ids if c in alive], "location_id": loc["id"] if loc else None,
                "shot": row["shot"], "angle": row["angle"], "aspect_ratio": row["aspect_ratio"], "comic_style": row["comic_style"],
                "bubbles": json.loads(row["bubbles"]), "image_id": image, "takes": takes,
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def all(self, ws: str = DEFAULT_WS) -> list[dict]:
        return [self.public(r, ws) for r in self.st.db.all("SELECT * FROM comic_panels WHERE workspace_id = ? ORDER BY created_at", (ws,))]

    def get(self, panel_id: str, ws: str = DEFAULT_WS) -> dict:
        return self.public(self._row(panel_id, ws), ws)

    def create(self, ws: str = DEFAULT_WS, title: str = "") -> dict:
        self.st.workspaces.get(ws)
        n = self.st.db.one("SELECT COUNT(*) AS n FROM comic_panels WHERE workspace_id = ?", (ws,))["n"]
        row = {"id": uuid.uuid4().hex, "workspace_id": ws, "title": (title.strip() or f"Panel {n + 1}")[:TITLE_MAX], "description": "",
               "character_ids": "[]", "location_id": None, "shot": "MS", "angle": "eye", "aspect_ratio": "4:3", "comic_style": "project",
               "bubbles": "[]", "image_id": None, "created_at": now(), "updated_at": now()}
        self.st.db.insert("comic_panels", row)
        return self.public(row, ws)

    def _clean_bubbles(self, bubbles: list[dict]) -> list[dict]:
        if len(bubbles) > MAX_BUBBLES:
            raise ServiceError(f"maksimal {MAX_BUBBLES} balon per panel", 422)
        seen = set()
        for b in bubbles:
            if b["kind"] not in KINDS:
                raise ServiceError(f"jenis balon harus salah satu dari {', '.join(KINDS)}", 422)
            if not b["text"].strip() or len(b["text"]) > TEXT_MAX:
                raise ServiceError(f"teks balon 1 sampai {TEXT_MAX} karakter", 422)
            if b["id"] in seen:
                raise ServiceError("id balon ganda", 422)
            seen.add(b["id"])
            if b["x"] + b["w"] > 1.0001 or b["y"] + b["h"] > 1.0001:
                raise ServiceError("balon keluar dari batas panel", 422)
        return bubbles

    def update(self, panel_id: str, patch: dict, ws: str = DEFAULT_WS) -> dict:
        row = self._row(panel_id, ws)
        cols: dict = {}
        if "title" in patch:
            if not 1 <= len(patch["title"].strip()) <= TITLE_MAX:
                raise ServiceError(f"judul 1 sampai {TITLE_MAX} karakter", 422)
            cols["title"] = patch["title"].strip()
        if "description" in patch:
            cols["description"] = patch["description"][:DESC_MAX]
        for key, allowed in (("shot", comic_prompt.SHOTS), ("angle", comic_prompt.ANGLES), ("comic_style", comic_prompt.STYLES), ("aspect_ratio", RATIOS)):
            if key in patch:
                if patch[key] not in allowed:
                    raise ServiceError(f"{key} harus salah satu dari {', '.join(allowed)}", 422)
                cols[key] = patch[key]
        if "character_ids" in patch:
            ids = patch["character_ids"]
            if len(ids) > MAX_CAST or len(set(ids)) != len(ids):
                raise ServiceError(f"maksimal {MAX_CAST} karakter berbeda per panel", 422)
            for cid in ids:
                self.st.get_character(cid, ws)
            cols["character_ids"] = json.dumps(ids)
        if "location_id" in patch:
            if patch["location_id"]:
                self.st.scenes._location(patch["location_id"], ws)
            cols["location_id"] = patch["location_id"]
        if "bubbles" in patch:
            cols["bubbles"] = json.dumps(self._clean_bubbles(patch["bubbles"]))
        if "image_id" in patch:
            if patch["image_id"] not in self._takes(panel_id):
                raise ServiceError("gambar bukan take panel ini", 422)
            cols["image_id"] = patch["image_id"]
        if cols:
            self.st.db.update("comic_panels", row["id"], {**cols, "updated_at": now()})
        return self.get(panel_id, ws)

    def delete(self, panel_id: str, ws: str = DEFAULT_WS) -> None:
        self._row(panel_id, ws)
        self.st.db.execute("DELETE FROM comic_panels WHERE id = ?", (panel_id,))   # take tetap di library

    # ---------- generate ----------
    def _alive(self, image_id: str | None, ws: str) -> bool:
        if not image_id:
            return False
        try:
            self.st.get_image(image_id, ws)
            return True
        except ServiceError:
            return False

    def plan(self, panel_id: str, model: str, ws: str = DEFAULT_WS) -> dict:
        """Satu sumber kebenaran gambar input + prompt; dipakai /api/estimate, pratinjau, dan generate."""
        st = self.st
        panel = self.get(panel_id, ws)
        project = st.workspaces.get(ws)
        warnings: list[str] = []
        loc = None
        if panel["location_id"]:
            loc = dict(st.scenes._location(panel["location_id"], ws))
            if loc["image_id"] and not self._alive(loc["image_id"], ws):
                warnings.append(f"gambar latar {loc['name']} sudah dihapus; latar hanya dijelaskan lewat teks")
                loc["image_id"] = None
        chars = []
        for cid in panel["character_ids"]:
            ch = st.get_character(cid, ws)
            image = ch["source_image_id"] if self._alive(ch["source_image_id"], ws) else None
            if not image:
                warnings.append(f"gambar karakter {ch['name']} sudah dihapus; karakter hanya dijelaskan lewat teks")
            chars.append({"name": ch["name"], "description": ch["description"], "image_id": image})
        inputs = ([loc["image_id"]] if loc and loc["image_id"] else []) + [c["image_id"] for c in chars if c["image_id"]]
        options = st.scenes._aspect_option(model, panel["aspect_ratio"])
        if not options:
            warnings.append(f"model {model} tidak menerima rasio {panel['aspect_ratio']}; rasio mengikuti bawaan model")
        st._validate_image_params(model, options, len(inputs))
        prompt = comic_prompt.build(panel, chars, loc, project["style"])
        if len(prompt) > 4000:
            raise ServiceError("prompt panel terlalu panjang; ringkas deskripsi", 422)
        return {"panel": panel, "inputs": inputs, "prompt": prompt, "options": options, "warnings": warnings}

    def preview(self, panel_id: str, model: str, ws: str = DEFAULT_WS) -> dict:
        p = self.plan(panel_id, model, ws)
        return {"prompt": p["prompt"], "inputs": p["inputs"], "options": p["options"], "warnings": p["warnings"]}

    def estimate(self, panel_id: str, model: str, ws: str = DEFAULT_WS):
        return self.st.estimate_image_job(model, n_inputs=len(self.plan(panel_id, model, ws)["inputs"]))

    def generate(self, panel_id: str, model: str, ws: str = DEFAULT_WS, confirmed_cost: float | None = None,
                 accept_unknown_cost: bool = False) -> dict:
        st = self.st
        with st._lock:
            p = self.plan(panel_id, model, ws)
            est = st.estimate_image_job(model, n_inputs=len(p["inputs"]))
            st.authorize(est, confirmed_cost, accept_unknown_cost)
            try:
                if p["inputs"]:
                    urls = [media.to_data_url(st.storage.resolve(st.get_image(i, ws)["path"]).read_bytes()) for i in p["inputs"]]
                    resp = st.client.edit_image(model, p["prompt"], urls, **p["options"])
                else:   # tanpa gambar sama sekali: teks ke gambar (plan 08)
                    resp = st.client.generate_image(model, p["prompt"], **p["options"])
            except OpenRouterError as exc:
                raise ServiceError(str(exc), 502) from exc
            made = st._store_edit_results(resp, p["inputs"][0] if p["inputs"] else None, p["prompt"], model, est, "comic_panel", ws)
            for img in made:
                st.db.execute("UPDATE images SET panel_id = ? WHERE id = ?", (panel_id, img["id"]))
            st.db.update("comic_panels", panel_id, {"image_id": made[0]["id"], "updated_at": now()})   # take baru langsung dipakai
        return self.get(panel_id, ws)
