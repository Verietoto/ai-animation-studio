"""Episode (baris `films`): adegan berurutan menjadi satu video (plan 05, adegan di plan 08).

Render memakai media.merge_videos (sama dengan merge_chain) di thread latar: API membalas 202
dan UI polling `render_status`. Satu render per film; film yang sedang dirender tidak boleh diubah/dihapus.
"""
import json
import re
import threading
import uuid
from pathlib import Path

from . import media
from .db import now
from .service import DEFAULT_WS, ServiceError

MAX_SCENES = 50
RENDER_TIMEOUT = 600.0        # detik per perintah ffmpeg
ASPECT_TOLERANCE = 0.02       # selisih rasio aspek yang masih dianggap sama
ASPECT_RE = re.compile(r"^\d{1,2}:\d{1,2}$")


class Films:
    def __init__(self, studio):
        self.st = studio

    # ---------- util ----------
    def _row(self, film_id: str, ws: str | None = DEFAULT_WS) -> dict:
        """ws=None hanya untuk berkas hasil render dan thread latar (tanpa batas workspace)."""
        sql, args = "SELECT * FROM films WHERE id = ?", [film_id]
        if ws is not None:
            sql, args = sql + " AND workspace_id = ?", [*args, ws]
        row = self.st.db.one(sql, tuple(args))
        if not row:
            raise ServiceError("film tidak ditemukan", 404)
        return row

    def _file(self, row: dict) -> Path | None:
        if not row["merged_path"]:
            return None
        try:
            path = self.st.storage.resolve(row["merged_path"])
        except ValueError:
            return None
        return path if path.exists() else None

    def _slots(self, film_id: str) -> list[str | None]:
        """Klip tiap adegan berurutan; None = adegan belum punya video."""
        return [r["clip_id"] for r in self.st.db.all("SELECT clip_id FROM scenes WHERE film_id = ? ORDER BY position", (film_id,))]

    def public(self, row: dict) -> dict:
        slots = self._slots(row["id"])
        ids = [c for c in slots if c]
        rendered = json.loads(row["rendered_ids"]) if row["rendered_ids"] else None
        has_file = self._file(row) is not None
        ready = self.st.db.one(
            "SELECT COUNT(*) AS n FROM scenes s JOIN clips c ON c.id = s.clip_id AND c.deleted_at IS NULL "
            "WHERE s.film_id = ? AND c.status = 'completed'", (row["id"],))["n"]
        planned = self.st.db.one("SELECT COALESCE(SUM(planned_seconds), 0) AS n FROM scenes WHERE film_id = ?", (row["id"],))["n"]
        return {"id": row["id"], "title": row["title"], "number": row["number"], "synopsis": row["synopsis"], "planned_seconds": planned,
                "aspect_ratio": row["aspect_ratio"], "clip_ids": ids, "scene_count": len(slots), "ready_count": ready,
                "render_status": row["render_status"], "render_error": row["render_error"], "has_file": has_file,
                "stale": has_file and rendered != ids, "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def file_path(self, film_id: str) -> Path:
        path = self._file(self._row(film_id, None))
        if path is None:
            raise ServiceError("film belum dirender", 404)
        return path

    def _clean_title(self, title: str) -> str:
        title = (title or "").strip()
        if not 1 <= len(title) <= 120:
            raise ServiceError("judul film 1 sampai 120 karakter", 422)
        return title

    # ---------- CRUD ----------
    def create(self, title: str, ws: str = DEFAULT_WS, number: int | None = None, synopsis: str = "") -> dict:
        stamp = now()
        if number is None:
            number = (self.st.db.one("SELECT COALESCE(MAX(number), 0) AS n FROM films WHERE workspace_id = ?", (ws,))["n"]) + 1
        film = {"id": uuid.uuid4().hex, "title": self._clean_title(title), "clip_ids": "[]", "render_status": "idle",
                "number": self._clean_number(number), "synopsis": self._clean_synopsis(synopsis),
                "created_at": stamp, "updated_at": stamp, "workspace_id": ws}
        self.st.db.insert("films", film)
        return self.public(self._row(film["id"], ws))

    @staticmethod
    def _clean_number(number) -> int:
        if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= 9999:
            raise ServiceError("nomor episode 1 sampai 9999", 422)
        return number

    @staticmethod
    def _clean_synopsis(text: str | None) -> str:
        text = (text or "").strip()
        if len(text) > 2000:
            raise ServiceError("sinopsis maksimal 2000 karakter", 422)
        return text

    def list_all(self, ws: str = DEFAULT_WS) -> list[dict]:   # bukan `list`: nama itu menutupi tipe list[...] di anotasi kelas
        return [self.public(r) for r in self.st.db.all(
            "SELECT * FROM films WHERE workspace_id = ? ORDER BY number, created_at LIMIT 200", (ws,))]

    def get(self, film_id: str, ws: str = DEFAULT_WS) -> dict:
        return self.public(self._row(film_id, ws))

    def update(self, film_id: str, title: str | None = None, ws: str = DEFAULT_WS, number: int | None = None,
               synopsis: str | None = None, aspect_ratio: str | None = None, script: str | None = None,
               previs_skipped: bool | None = None) -> dict:
        with self.st._lock:
            row = self._row(film_id, ws)
            if row["render_status"] == "rendering":
                raise ServiceError("film sedang dirender; tunggu selesai", 409)
            values: dict = {"updated_at": now()}
            if title is not None:
                values["title"] = self._clean_title(title)
            if number is not None:
                values["number"] = self._clean_number(number)
            if synopsis is not None:
                values["synopsis"] = self._clean_synopsis(synopsis)
            if script is not None:   # plan 15: naskah utuh episode dengan mention @[karakter] / #[latar]
                from . import script as script_mod
                values["script"] = script_mod.clean_script(script)
            if previs_skipped is not None:
                values["previs_skipped"] = 1 if previs_skipped else 0
            if aspect_ratio is not None:
                if not ASPECT_RE.match(aspect_ratio):
                    raise ServiceError("rasio aspek harus berbentuk 16:9", 422)
                values["aspect_ratio"] = aspect_ratio
            self.st.db.update("films", film_id, values)
        return self.get(film_id, ws)

    def delete(self, film_id: str, ws: str = DEFAULT_WS) -> None:
        with self.st._lock:
            row = self._row(film_id, ws)
            if row["render_status"] == "rendering":
                raise ServiceError("film sedang dirender; tunggu selesai", 409)
            with self.st.db.transaction() as tx:
                for table in ("images", "clips"):   # hasil generate tetap di library, hanya lepas dari adegan
                    tx.execute(f"UPDATE {table} SET scene_id = NULL WHERE scene_id IN (SELECT id FROM scenes WHERE film_id = ?)", (film_id,))
                tx.execute("DELETE FROM scene_cast WHERE scene_id IN (SELECT id FROM scenes WHERE film_id = ?)", (film_id,))
                for t in ("scene_beats", "beat_versions"):
                    tx.execute(f"DELETE FROM {t} WHERE scene_id IN (SELECT id FROM scenes WHERE film_id = ?)", (film_id,))
                tx.execute("DELETE FROM scenes WHERE film_id = ?", (film_id,))
                tx.execute("DELETE FROM film_characters WHERE film_id = ?", (film_id,))
                tx.execute("DELETE FROM film_locations WHERE film_id = ?", (film_id,))
                tx.execute("DELETE FROM films WHERE id = ?", (film_id,))
        if (path := self._file(row)):
            path.unlink(missing_ok=True)

    def detach_clip(self, clip_id: str) -> None:
        """Lepas klip dari semua adegan (klip dihapus; adegan dan naskahnya tetap). Bila ada episode terkait yang sedang dirender, tolak tanpa mengubah apa pun."""
        busy = self.st.db.one("SELECT 1 FROM scenes s JOIN films f ON f.id = s.film_id "
                              "WHERE s.clip_id = ? AND f.render_status = 'rendering'", (clip_id,))
        if busy:
            raise ServiceError("klip dipakai film yang sedang dirender; tunggu selesai", 409)
        self.st.db.execute("UPDATE scenes SET clip_id = NULL, updated_at = ? WHERE clip_id = ?", (now(), clip_id))

    # ---------- detail: peringatan rasio + durasi ----------
    def detail(self, film_id: str, ws: str = DEFAULT_WS) -> dict:
        film = self.get(film_id, ws)
        durations: dict[str, float] = {}
        warnings: list[dict] = []
        sizes: dict[str, tuple[int, int] | None] = {}
        slots = self._slots(film_id)
        for cid in dict.fromkeys(c for c in slots if c):
            clip = self.st.db.one("SELECT path, status, duration FROM clips WHERE id = ? AND deleted_at IS NULL AND workspace_id = ?",
                                  (cid, ws))
            if not clip or clip["status"] != "completed" or not clip["path"]:
                sizes[cid] = None
                continue
            try:
                info = media.probe(self.st.storage.resolve(clip["path"]))
            except (media.MediaError, ValueError, OSError):
                sizes[cid] = None
                continue
            sizes[cid] = (info["width"], info["height"])
            durations[cid] = info["duration"]
            if clip["duration"] is None:   # klip lama: durasi diisi malas
                self.st.db.update("clips", cid, {"duration": info["duration"]})
        first = next((sizes[c] for c in slots if c and sizes.get(c)), None)
        for n, cid in enumerate(slots, 1):
            size = sizes.get(cid) if cid else None
            if size is None:
                warnings.append({"scene": n, "kind": "unplayable", "message": f"adegan {n} belum punya video yang selesai"})
            elif first and abs((size[0] / size[1]) / (first[0] / first[1]) - 1) > ASPECT_TOLERANCE:
                warnings.append({"scene": n, "kind": "aspect",
                                 "message": f"adegan {n} ({size[0]}×{size[1]}) rasionya beda dari adegan pertama; akan diberi bar hitam"})
        return {**film, "scenes": self.st.scenes.list_for(film_id), "durations": durations, "warnings": warnings}

    # ---------- render ----------
    def _playable(self, ids: list[str | None], ws: str = DEFAULT_WS) -> list[Path]:
        paths, bad = [], []
        for n, cid in enumerate(ids, 1):
            clip = self.st.db.one("SELECT path, status FROM clips WHERE id = ? AND deleted_at IS NULL AND workspace_id = ?",
                                  (cid, ws)) if cid else None
            try:
                path = self.st.storage.resolve(clip["path"]) if clip and clip["status"] == "completed" and clip["path"] else None
            except ValueError:
                path = None
            if path is None or not path.exists():
                bad.append(n)
            else:
                paths.append(path)
        if bad:
            raise ServiceError(f"adegan {', '.join(map(str, bad))} belum punya video yang selesai", 409)
        return paths

    def render(self, film_id: str, ws: str = DEFAULT_WS) -> dict:
        with self.st._lock:
            row = self._row(film_id, ws)
            if row["render_status"] == "rendering":
                raise ServiceError("film sedang dirender", 409)
            ids = self._slots(film_id)
            if not ids:
                raise ServiceError("storyboard masih kosong", 422)
            if not media.ffmpeg_available():
                raise ServiceError("ffmpeg/ffprobe tidak ditemukan di server", 503)
            paths = self._playable(ids, ws)
            self.st.db.update("films", film_id, {"render_status": "rendering", "render_error": None, "updated_at": now()})
        threading.Thread(target=self._render_job, args=(film_id, ids, paths), daemon=True).start()
        return self.get(film_id, ws)

    def _render_job(self, film_id: str, ids: list[str], paths: list[Path]) -> None:
        out = self.st.storage.new_path(".mp4")
        try:
            media.merge_videos(paths, out, RENDER_TIMEOUT)
        except Exception as exc:   # apa pun yang gagal harus mengakhiri status "rendering", jangan menggantung
            out.unlink(missing_ok=True)
            self.st.db.update("films", film_id, {"render_status": "failed", "render_error": f"render gagal: {exc}"[:500],
                                                 "updated_at": now()})
            return
        old = self._file(self._row(film_id, None))   # thread latar: tanpa batas workspace
        self.st.db.update("films", film_id, {"render_status": "done", "render_error": None, "merged_path": str(out),
                                             "rendered_ids": json.dumps(ids), "updated_at": now()})
        if old:
            old.unlink(missing_ok=True)   # tidak menumpuk file render lama

    def recover(self) -> None:
        """Render yang terputus karena server mati tidak boleh tampak 'rendering' selamanya."""
        self.st.db.execute("UPDATE films SET render_status = 'failed', render_error = 'render terputus (server dimulai ulang)' "
                           "WHERE render_status = 'rendering'")
