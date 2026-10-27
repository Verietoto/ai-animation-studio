"""Alur pembuatan episode per langkah (plan 15): pemeran/latar episode, naskah dengan mention, AI naskah & pemecahan adegan.

Pemeran dan latar episode adalah daftar pilihan; adegan memakai sebagian darinya (maks 3 pemeran per adegan). Semua akses
dibatasi workspace lewat film induk. Panggilan AI lewat `textai` (biaya masuk `text_jobs` dan anggaran harian).
"""
from . import beats as beats_mod
from . import script, script_format, textai
from .db import now
from .service import DEFAULT_WS, ServiceError

MAX_EPISODE_CHARACTERS = 30
MAX_EPISODE_LOCATIONS = 40
SCRIPT_TOKENS, SPLIT_TOKENS = 4000, 12000


class Journey:
    def __init__(self, studio):
        self.st = studio

    # ---------- pemeran & latar episode ----------
    def _film(self, film_id: str, ws: str) -> dict:
        return self.st.films._row(film_id, ws)

    def characters(self, film_id: str) -> list[dict]:
        rows = self.st.db.all(
            "SELECT c.id, c.name, c.description, c.source_image_id AS image_id, "
            "(SELECT COUNT(*) FROM character_images ci WHERE ci.character_id = c.id) AS n_images "
            "FROM film_characters fc JOIN characters c ON c.id = fc.character_id WHERE fc.film_id = ? ORDER BY fc.position", (film_id,))
        return [{**r, "has_sheet": r.pop("n_images") > 1} for r in rows]

    def locations(self, film_id: str) -> list[dict]:
        return self.st.db.all(
            "SELECT l.id, l.name, l.description, l.image_id FROM film_locations fl JOIN locations l ON l.id = fl.location_id "
            "WHERE fl.film_id = ? ORDER BY fl.position", (film_id,))

    def _used(self, film_id: str) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
        """{character_id: [nomor adegan]}, {location_id: [nomor adegan]} yang memakainya di episode ini."""
        chars: dict[str, list[int]] = {}
        locs: dict[str, list[int]] = {}
        for r in self.st.db.all("SELECT sc.character_id, s.position FROM scene_cast sc JOIN scenes s ON s.id = sc.scene_id "
                                "WHERE s.film_id = ? ORDER BY s.position", (film_id,)):
            chars.setdefault(r["character_id"], []).append(r["position"] + 1)
        for r in self.st.db.all("SELECT location_id, position FROM scenes WHERE film_id = ? AND location_id IS NOT NULL ORDER BY position",
                                (film_id,)):
            locs.setdefault(r["location_id"], []).append(r["position"] + 1)
        return chars, locs

    def set_cast(self, film_id: str, character_ids: list[str], location_ids: list[str], ws: str = DEFAULT_WS,
                 release: bool = False) -> dict:
        """Ganti daftar pemeran/latar episode. Yang dikeluarkan tapi masih dipakai adegan ditolak (409), kecuali `release`."""
        character_ids, location_ids = list(dict.fromkeys(character_ids)), list(dict.fromkeys(location_ids))
        if len(character_ids) > MAX_EPISODE_CHARACTERS or len(location_ids) > MAX_EPISODE_LOCATIONS:
            raise ServiceError(f"maksimal {MAX_EPISODE_CHARACTERS} pemeran dan {MAX_EPISODE_LOCATIONS} latar per episode", 422)
        with self.st._lock:
            self._film(film_id, ws)
            self.st.scenes._editable(film_id)
            chars = [self.st.get_character(cid, ws) for cid in character_ids]   # 404 lintas workspace
            locs = [self.st.scenes._location(lid, ws) for lid in location_ids]
            for kind, rows in (("karakter", chars), ("latar", locs)):
                seen: dict[str, str] = {}
                for r in rows:
                    if "[" in r["name"] or "]" in r["name"]:
                        raise ServiceError(f"nama {kind} \"{r['name']}\" memuat [ atau ]; ganti namanya dulu agar bisa di-mention", 422)
                    k = script.key(r["name"])
                    if k in seen:
                        raise ServiceError(f"dua {kind} bernama \"{r['name']}\" di episode ini; ganti salah satu namanya dulu", 422)
                    seen[k] = r["id"]
            used_c, used_l = self._used(film_id)
            gone_c = [c for c in used_c if c not in character_ids]
            gone_l = [l for l in used_l if l not in location_ids]
            if (gone_c or gone_l) and not release:
                nums = sorted({n for c in gone_c for n in used_c[c]} | {n for l in gone_l for n in used_l[l]})
                raise ServiceError("masih dipakai adegan " + ", ".join(map(str, nums)) + "; lepas dari adegan itu dulu atau pilih "
                                   "\"lepas dari adegan\"", 409)
            with self.st.db.transaction() as tx:
                for cid in gone_c:
                    tx.execute("DELETE FROM scene_cast WHERE character_id = ? AND scene_id IN (SELECT id FROM scenes WHERE film_id = ?)",
                               (cid, film_id))
                for lid in gone_l:
                    tx.execute("UPDATE scenes SET location_id = NULL WHERE location_id = ? AND film_id = ?", (lid, film_id))
                tx.execute("DELETE FROM film_characters WHERE film_id = ?", (film_id,))
                tx.execute("DELETE FROM film_locations WHERE film_id = ?", (film_id,))
                for pos, cid in enumerate(character_ids):
                    tx.execute("INSERT INTO film_characters VALUES (?, ?, ?)", (film_id, cid, pos))
                for pos, lid in enumerate(location_ids):
                    tx.execute("INSERT INTO film_locations VALUES (?, ?, ?)", (film_id, lid, pos))
                tx.execute("UPDATE films SET updated_at = ? WHERE id = ?", (now(), film_id))
        return self.state(film_id, ws)

    def ensure(self, film_id: str, character_ids: list[str], location_id: str | None) -> None:
        """Pemeran/latar yang dipakai adegan otomatis ikut daftar episode (alur lama lewat Mode lanjutan). Tanpa validasi nama."""
        with self.st._lock:
            for cid in dict.fromkeys(character_ids):
                if not self.st.db.one("SELECT 1 FROM film_characters WHERE film_id = ? AND character_id = ?", (film_id, cid)):
                    pos = self.st.db.one("SELECT COALESCE(MAX(position), -1) + 1 AS n FROM film_characters WHERE film_id = ?", (film_id,))["n"]
                    self.st.db.execute("INSERT INTO film_characters VALUES (?, ?, ?)", (film_id, cid, pos))
            if location_id and not self.st.db.one("SELECT 1 FROM film_locations WHERE film_id = ? AND location_id = ?", (film_id, location_id)):
                pos = self.st.db.one("SELECT COALESCE(MAX(position), -1) + 1 AS n FROM film_locations WHERE film_id = ?", (film_id,))["n"]
                self.st.db.execute("INSERT INTO film_locations VALUES (?, ?, ?)", (film_id, location_id, pos))

    def forget_character(self, character_id: str) -> None:
        self.st.db.execute("DELETE FROM film_characters WHERE character_id = ?", (character_id,))

    def rename_location(self, location_id: str, old: str, new: str) -> None:
        """Mention #[nama lama] di naskah episode yang memakai latar ini ikut diganti; tanda 'naskah berubah' tidak ikut menyala."""
        for r in self.st.db.all("SELECT f.id, f.script, f.script_split_hash FROM films f JOIN film_locations fl ON fl.film_id = f.id "
                                "WHERE fl.location_id = ?", (location_id,)):
            text = script.rename(r["script"], "location", old, new)
            if text != r["script"]:
                values = {"script": text, "updated_at": now()}
                if r["script_split_hash"] == script.digest(r["script"]):
                    values["script_split_hash"] = script.digest(text)
                self.st.db.update("films", r["id"], values)
        for r in self.st.db.all("SELECT id, prompt FROM scenes WHERE location_id = ? AND prompt IS NOT NULL", (location_id,)):
            self.st.db.update("scenes", r["id"], {"prompt": script.rename(r["prompt"], "location", old, new)})   # prompt adegan ikut (plan 18 Revisi 8)

    # ---------- keadaan alur (untuk stepper) ----------
    def state(self, film_id: str, ws: str = DEFAULT_WS) -> dict:
        row = self._film(film_id, ws)
        chars, locs = self.characters(film_id), self.locations(film_id)
        agg = self.st.db.one(
            "SELECT COUNT(*) AS scenes, COALESCE(SUM(blockout IS NOT NULL), 0) AS blockout, COALESCE(SUM(previs_ref_id IS NOT NULL), 0) AS previs, "
            "COALESCE(SUM(keyframe_image_id IS NOT NULL), 0) AS keyframe, COALESCE(SUM(clip_id IS NOT NULL), 0) AS video, "
            "COALESCE(SUM(location_id IS NULL), 0) AS no_location, COALESCE(SUM(planned_seconds), 0) AS planned "
            "FROM scenes WHERE film_id = ?", (film_id,))
        film = self.st.films.public(row)
        changed = bool(row["script_split_hash"]) and row["script_split_hash"] != script.digest(row["script"])
        return {"film_id": film_id, "script": row["script"], "script_changed": changed, "previs_skipped": bool(row["previs_skipped"]),
                "characters": chars, "locations": locs, "mentions": script.analyze(row["script"], chars, locs), "format": self.format_info(film_id, ws),
                "progress": {**agg, "video_ready": film["ready_count"], "rendered": film["has_file"] and not film["stale"],
                             "render_status": film["render_status"]}}

    # ---------- AI: naskah ----------
    def _script_prompt(self, film_id: str, ws: str) -> tuple[str, str]:
        row = self._film(film_id, ws)
        if not row["synopsis"].strip() and not row["script"].strip():
            raise ServiceError("isi sinopsis atau tulis sedikit naskah dulu", 422)
        return script.SCRIPT_SYSTEM, script.script_user(row["title"], row["synopsis"], self.characters(film_id), self.locations(film_id),
                                                         row["script"][:6000])

    def script_estimate(self, film_id: str, ws: str = DEFAULT_WS, model: str | None = None):
        system, user = self._script_prompt(film_id, ws)
        return textai.estimate(self.st, system, user, SCRIPT_TOKENS, min_out=1500, model=model)

    def script_draft(self, film_id: str, ws: str = DEFAULT_WS, confirmed_cost: float | None = None,
                     accept_unknown_cost: bool = False, model: str | None = None) -> dict:
        """AI menulis naskah. Hasil berupa DRAF (tidak disimpan); biaya tercatat di text_jobs."""
        with self.st._lock:
            system, user = self._script_prompt(film_id, ws)
            est = textai.estimate(self.st, system, user, SCRIPT_TOKENS, min_out=1500, model=model)
            raw, cost = textai.ask(self.st, "episode_script", system, user, SCRIPT_TOKENS, est, ws, confirmed_cost, accept_unknown_cost,
                                   model=model)
        text = raw.get("script")
        if not isinstance(text, str) or not text.strip():
            raise ServiceError("AI tidak menghasilkan naskah; coba lagi", 502)
        return self._check_script(text, film_id, ws, cost, est, system, user, model, confirmed_cost, accept_unknown_cost)

    def _check_script(self, text, film_id, ws, cost, est, system, user, model, confirmed_cost, accept_unknown_cost,
                      kind: str = "episode_script", max_tokens: int = SCRIPT_TOKENS) -> dict:
        """Naskah AI wajib berformat Seedance (plan 18 Revisi 5): diurai; salah → ulang SEKALI dengan daftar galat, lalu 502."""
        chars, locs = self.characters(film_id), self.locations(film_id)
        total = cost or 0.0
        for attempt in (1, 2):
            text = text.strip()
            parsed = script_format.parse(text, chars, locs) if script_format.is_formatted(text) else \
                {"scenes": [], "warnings": [], "errors": ["naskah tidak memakai format blok adegan (FORMAT: dan SHOT n — m:ss to m:ss)"]}
            if not parsed["errors"]:
                warnings = list(parsed["warnings"])
                if len(text) > script.MAX_SCRIPT:
                    text, warnings = text[:script.MAX_SCRIPT], [*warnings, f"naskah dipotong sampai {script.MAX_SCRIPT:,} karakter"]
                return {"script": text, "warnings": warnings, "cost": total or None, "estimated_cost": est.high,
                        "attempts": attempt, "scenes": len(parsed["scenes"])}
            if attempt == 2:
                raise ServiceError("AI menulis naskah yang tidak sesuai format shot Seedance (" + "; ".join(parsed["errors"][:3]) + "); "
                                   "coba lagi atau pilih model lain", 502)
            with self.st._lock:
                raw, c2 = textai.ask(self.st, kind, system, user + "\n\nYour previous script was rejected:\n- " +
                                     "\n- ".join(parsed["errors"][:8]) + "\nWrite the whole script again and fix every point.",
                                     max_tokens, est, ws, confirmed_cost, accept_unknown_cost, model=model)
            total += c2 or 0.0
            text = raw.get("script") if isinstance(raw.get("script"), str) else ""

    # ---------- AI: ubah naskah yang sudah ada (plan 18 Revisi 7) ----------
    def _revise_script_prompt(self, film_id: str, ws: str, instruction: str) -> tuple[str, str, int, dict]:
        row = self._film(film_id, ws)
        if not row["script"].strip():
            raise ServiceError("naskah masih kosong; tulis dengan AI dulu atau ketik sendiri", 422)
        return (script.REVISE_SCRIPT_SYSTEM, script.revise_user(row["title"], row["synopsis"], self.characters(film_id), self.locations(film_id),
                                                                  row["script"], instruction), script.revise_tokens(row["script"]), row)

    def script_revise_estimate(self, film_id: str, ws: str = DEFAULT_WS, model: str | None = None):
        """Instruksi dipadatkan ke batas panjang: estimasi konstan dan sama dengan yang dihitung saat generate."""
        system, user, tokens, _ = self._revise_script_prompt(film_id, ws, "x" * script.INSTRUCTION_MAX)
        return textai.estimate(self.st, system, user, tokens, min_out=min(tokens, 3000), model=model)

    def script_revise(self, film_id: str, instruction: str, ws: str = DEFAULT_WS, confirmed_cost: float | None = None,
                      accept_unknown_cost: bool = False, model: str | None = None) -> dict:
        instruction = (instruction or "").strip()
        if not instruction:
            raise ServiceError("tulis dulu apa yang ingin diubah", 422)
        if len(instruction) > script.INSTRUCTION_MAX:
            raise ServiceError(f"instruksi maksimal {script.INSTRUCTION_MAX} karakter", 422)
        with self.st._lock:
            system, user, tokens, row = self._revise_script_prompt(film_id, ws, instruction)
            _, padded, _, _ = self._revise_script_prompt(film_id, ws, "x" * script.INSTRUCTION_MAX)
            est = textai.estimate(self.st, system, padded, tokens, min_out=min(tokens, 3000), model=model)
            raw, cost = textai.ask(self.st, "script_revise", system, user, tokens, est, ws, confirmed_cost, accept_unknown_cost, model=model)
        text = raw.get("script")
        if not isinstance(text, str) or not text.strip():
            raise ServiceError("AI tidak menghasilkan naskah; coba lagi", 502)
        out = self._check_script(text, film_id, ws, cost, est, system, user, model, confirmed_cost, accept_unknown_cost,
                                 kind="script_revise", max_tokens=tokens)
        return {**out, **script_format.compare(row["script"], out["script"]), "format_before": script_format.is_formatted(row["script"])}

    # ---------- naskah berformat → adegan + beat (gratis, tanpa AI) ----------
    def format_info(self, film_id: str, ws: str = DEFAULT_WS) -> dict:
        row = self._film(film_id, ws)
        if not script_format.is_formatted(row["script"]):
            return {"detected": False, "scenes": 0, "shots": 0, "errors": [], "warnings": []}
        p = script_format.parse(row["script"], self.characters(film_id), self.locations(film_id))
        return {"detected": True, "scenes": len(p["scenes"]), "shots": sum(len(s["beats"]) for s in p["scenes"]),
                "errors": p["errors"], "warnings": p["warnings"]}

    def split_format(self, film_id: str, ws: str = DEFAULT_WS) -> dict:
        """Draf adegan + beat dari naskah berformat. Tanpa AI, tanpa biaya. Adegan yang gagal diurai membuat seluruh draf ditolak (422)."""
        row = self._film(film_id, ws)
        if not script_format.is_formatted(row["script"]):
            raise ServiceError("naskah belum memakai format shot Seedance (FORMAT: dan SHOT n — m:ss to m:ss)", 422)
        p = script_format.parse(row["script"], self.characters(film_id), self.locations(film_id))
        if p["errors"]:
            raise ServiceError("naskah berformat punya masalah: " + "; ".join(p["errors"][:5]), 422, {"errors": p["errors"]})
        return {"scenes": p["scenes"], "warnings": p["warnings"], "cost": 0.0, "estimated_cost": 0.0, "source": "format"}

    # ---------- AI: pecah naskah jadi adegan ----------
    def _split_prompt(self, film_id: str, ws: str) -> tuple[str, str, list[dict], list[dict], dict]:
        row = self._film(film_id, ws)
        if not row["script"].strip():
            raise ServiceError("tulis naskah dulu", 422)
        chars, locs = self.characters(film_id), self.locations(film_id)
        return script.SPLIT_SYSTEM, script.split_user(row["script"], chars, locs, row["aspect_ratio"]), chars, locs, row

    def split_estimate(self, film_id: str, ws: str = DEFAULT_WS, model: str | None = None):
        system, user, *_ = self._split_prompt(film_id, ws)
        return textai.estimate(self.st, system, user, SPLIT_TOKENS, min_out=3000, model=model)

    def split_draft(self, film_id: str, ws: str = DEFAULT_WS, confirmed_cost: float | None = None,
                    accept_unknown_cost: bool = False, model: str | None = None) -> dict:
        """AI memecah naskah menjadi adegan. DRAF saja: dibuang id di luar pemeran/latar episode, tidak ada entitas baru."""
        with self.st._lock:
            system, user, chars, locs, _ = self._split_prompt(film_id, ws)
            est = textai.estimate(self.st, system, user, SPLIT_TOKENS, min_out=3000, model=model)
            raw, cost = textai.ask(self.st, "episode_split", system, user, SPLIT_TOKENS, est, ws, confirmed_cost, accept_unknown_cost,
                                   model=model)
        scenes, warnings = script.clean_split(raw.get("scenes"), [c["id"] for c in chars], [l["id"] for l in locs])
        if not scenes:
            raise ServiceError("AI tidak menghasilkan adegan; coba lagi", 502)
        return {"scenes": scenes, "warnings": warnings, "cost": cost, "estimated_cost": est.high}

    def apply_split(self, film_id: str, draft: list[dict], mode: str, ws: str = DEFAULT_WS) -> dict:
        """Terapkan draf. Draf divalidasi ULANG terhadap pemeran/latar episode saat ini. 'replace' hanya bila tak ada adegan berhasil."""
        if mode not in ("append", "replace"):
            raise ServiceError("mode harus append atau replace", 422)
        with self.st._lock:
            row = self._film(film_id, ws)
            sc = self.st.scenes
            sc._editable(film_id)
            scenes, warnings = script.clean_split(draft, [c["id"] for c in self.characters(film_id)], [l["id"] for l in self.locations(film_id)])
            if not scenes:
                raise ServiceError("tidak ada adegan untuk diterapkan", 422)
            for n, item in enumerate(scenes, 1):   # semua beat divalidasi SEBELUM adegan pertama dibuat (tidak ada penerapan sebagian)
                if "beats" in item:
                    try:
                        item["beats"], bw = beats_mod.clean(item["beats"], {c["character_id"] for c in item["cast"]}, item["planned_seconds"])
                    except ServiceError as exc:
                        raise ServiceError(f"adegan {n}: {exc}", 422) from exc
                    warnings.extend(f"adegan {n}: {w}" for w in bw)
            existing = sc._order(film_id)
            if mode == "append":
                if len(existing) + len(scenes) > script.MAX_SCENES:
                    raise ServiceError(f"episode akan melebihi {script.MAX_SCENES} adegan", 422)
            else:
                blocked = [n for n, sid in enumerate(existing, 1) if self.st.db.one(
                    "SELECT 1 FROM scenes WHERE id = ? AND (keyframe_image_id IS NOT NULL OR clip_id IS NOT NULL "
                    "OR blockout IS NOT NULL OR previs_ref_id IS NOT NULL)", (sid,))]
                if blocked:
                    raise ServiceError("adegan " + ", ".join(map(str, blocked)) + " sudah punya keyframe/video/previs; pilih tambahkan di akhir "
                                       "atau hapus adegan itu dulu", 409)
                for sid in existing:
                    sc.delete(sid, ws)
            for item in scenes:
                made = sc.add(film_id, ws, inherit=False)
                sc.update(made["id"], {"location_id": item["location_id"], "time_of_day": item["time_of_day"], "camera": item["camera"],
                                       "dialogue": item["dialogue"], "extra_prompt": item["extra_prompt"],
                                       "planned_seconds": item["planned_seconds"], "cast": item["cast"],
                                       "script_excerpt": item["excerpt"]}, ws)
                if item.get("beats"):
                    self.st.beats.replace(made["id"], item["beats"], "dari naskah berformat", ws)
            self.st.db.update("films", film_id, {"script_split_hash": script.digest(row["script"]), "updated_at": now()})
        return {"scenes": sc.list_for(film_id), "warnings": warnings}
