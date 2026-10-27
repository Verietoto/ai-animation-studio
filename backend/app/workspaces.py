"""Workspace (plan 07): pemisah gambar, karakter, klip, film, dan referensi per proyek.

Workspace "Utama" (id `main`) dibuat oleh migrasi dan memuat semua data lama. Salin lintas workspace hanya untuk gambar
dan karakter: file digandakan, biaya salinan dikosongkan (tidak dibayar ulang), dan seluruhnya atomik.
"""
import re
import uuid

from .db import now
from .service import DEFAULT_WS, ServiceError

NAME_MAX = 60
MAX_COPY_ITEMS = 100
_COPY_SUFFIX = re.compile(r"\s\(salinan(?: \d+)?\)$")
RATIOS = ("1:1", "3:4", "9:16", "4:3", "16:9", "21:9", "9:21")   # rasio Seedance di OpenRouter
RESOLUTIONS = ("480p", "720p", "1080p", "4K")
STYLE_MAX = 500
# Storyboard v2 dikunci ke keluarga Seedance 2.0 (format request referensi yang sama); model lain tetap bisa dipakai di alur lama
V2_VIDEO_MODELS = ("bytedance/seedance-2.0", "bytedance/seedance-2.0-fast", "bytedance/seedance-2.0-mini")
GENRE_MAX = 80
SETTING_FIELDS = {"video_model", "video_resolution", "aspect_ratio", "generate_audio", "image_model", "style", "genre"}


class Workspaces:
    def __init__(self, studio):
        self.st = studio

    # ---------- util ----------
    def _clean(self, name: str) -> str:
        name = (name or "").strip()
        if not 1 <= len(name) <= NAME_MAX:
            raise ServiceError(f"nama workspace 1 sampai {NAME_MAX} karakter", 422)
        return name

    def get(self, ws_id: str) -> dict:
        """Workspace aktif (tidak diarsip). Kode `workspace_missing` memberi tahu klien untuk kembali ke Utama."""
        row = self.st.db.one("SELECT * FROM workspaces WHERE id = ? AND archived_at IS NULL AND deleted_at IS NULL", (ws_id,))
        if not row:
            raise ServiceError("workspace tidak ditemukan atau sudah diarsip", 404, {"code": "workspace_missing"})
        return row

    def _get_any(self, ws_id: str) -> dict:
        """Workspace yang belum dihapus, aktif maupun diarsip (untuk pulihkan/hapus)."""
        row = self.st.db.one("SELECT * FROM workspaces WHERE id = ? AND deleted_at IS NULL", (ws_id,))
        if not row:
            raise ServiceError("workspace tidak ditemukan", 404, {"code": "workspace_missing"})
        return row

    def _counts(self, ws_id: str) -> dict:
        db = self.st.db
        one = lambda sql: db.one(sql, (ws_id,))["n"]   # noqa: E731
        return {"images": one("SELECT COUNT(*) AS n FROM images WHERE workspace_id = ? AND deleted_at IS NULL"),
                "clips": one("SELECT COUNT(*) AS n FROM clips WHERE workspace_id = ? AND deleted_at IS NULL"),
                "characters": one("SELECT COUNT(*) AS n FROM characters WHERE workspace_id = ?"),
                "films": one("SELECT COUNT(*) AS n FROM films WHERE workspace_id = ?")}

    def public(self, row: dict) -> dict:
        return {"id": row["id"], "name": row["name"], "archived": bool(row["archived_at"]),
                "created_at": row["created_at"], "counts": self._counts(row["id"])}

    # ---------- pengaturan proyek (plan 18) ----------
    def _v2_assets(self, ws_id: str) -> dict:
        db = self.st.db
        return {"beat_images": db.one("SELECT COUNT(*) AS n FROM images WHERE workspace_id = ? AND beat_id IS NOT NULL "
                                      "AND deleted_at IS NULL", (ws_id,))["n"],
                "clips": db.one("SELECT COUNT(*) AS n FROM clips WHERE workspace_id = ? AND kind = 'storyboard' "
                                "AND deleted_at IS NULL", (ws_id,))["n"]}

    def settings(self, ws_id: str) -> dict:
        row = self.get(ws_id)
        assets = self._v2_assets(ws_id)
        return {"allowed_video_models": list(V2_VIDEO_MODELS), "video_model": row["video_model"], "video_resolution": row["video_resolution"],
                "aspect_ratio": row["aspect_ratio"], "generate_audio": bool(row["generate_audio"]),
                "image_model": row["image_model"], "style": row["style"], "genre": row["genre"] or "",
                "ratio_locked": bool(assets["beat_images"] or assets["clips"]), "v2_assets": assets,
                "mismatched_films": self.st.db.one("SELECT COUNT(*) AS n FROM films WHERE workspace_id = ? AND aspect_ratio != ?",
                                                   (ws_id, row["aspect_ratio"]))["n"]}

    def update_settings(self, ws_id: str, patch: dict, confirm_sync: bool = False) -> dict:
        """Satu sumber rasio: mengubah rasio proyek menyelaraskan `films.aspect_ratio` di workspace ini (grill 18 no. 1)."""
        with self.st._lock:
            row = self.get(ws_id)
            new = {k: v for k, v in patch.items() if v is not None or k == "image_model"}
            if "video_model" in new:
                if new["video_model"] not in V2_VIDEO_MODELS:
                    raise ServiceError("Storyboard v2 hanya memakai Seedance 2.0 (2.0, 2.0 Fast, atau 2.0 Mini)", 422)
                info = next((m for m in self.st.video_models() if m.get("id") == new["video_model"]), None)
                if not info:
                    raise ServiceError("model video tidak tersedia di OpenRouter", 422)
            model = new.get("video_model", row["video_model"])
            if "video_resolution" in new or "video_model" in new:
                res = new.get("video_resolution", row["video_resolution"])
                if res not in RESOLUTIONS:
                    raise ServiceError(f"resolusi harus salah satu dari {', '.join(RESOLUTIONS)}", 422)
                info = next((m for m in self.st.video_models() if m.get("id") == model), None)
                supported = (info or {}).get("supported_resolutions")
                if supported and res not in supported and "video_resolution" in new:
                    raise ServiceError(f"model {model} hanya mendukung resolusi {', '.join(supported)}", 422)
            if new.get("image_model"):
                if not any(m.get("id") == new["image_model"] for m in self.st.image_models()):
                    raise ServiceError("model gambar tidak tersedia", 422)
            if "style" in new and len(new["style"]) > STYLE_MAX:
                raise ServiceError(f"gaya maksimal {STYLE_MAX} karakter", 422)
            if "genre" in new and len(new["genre"]) > GENRE_MAX:
                raise ServiceError(f"genre maksimal {GENRE_MAX} karakter", 422)
            changed_films = 0
            if "aspect_ratio" in new and new["aspect_ratio"] != row["aspect_ratio"]:
                if new["aspect_ratio"] not in RATIOS:
                    raise ServiceError(f"rasio harus salah satu dari {', '.join(RATIOS)}", 422)
                assets = self._v2_assets(ws_id)
                if assets["beat_images"] or assets["clips"]:
                    raise ServiceError(f"rasio terkunci: proyek sudah punya {assets['beat_images']} gambar beat dan "
                                       f"{assets['clips']} klip Storyboard v2", 409, {"v2_assets": assets})
            if "aspect_ratio" in new and new["aspect_ratio"] in RATIOS:
                db = self.st.db
                differ = db.one("SELECT COUNT(*) AS n FROM films WHERE workspace_id = ? AND aspect_ratio != ?",
                                (ws_id, new["aspect_ratio"]))["n"]
                with_assets = db.one(
                    "SELECT COUNT(DISTINCT f.id) AS n FROM films f JOIN scenes s ON s.film_id = f.id "
                    "WHERE f.workspace_id = ? AND f.aspect_ratio != ? AND (s.keyframe_image_id IS NOT NULL OR s.clip_id IS NOT NULL)",
                    (ws_id, new["aspect_ratio"]))["n"]
                if with_assets and not confirm_sync:
                    raise ServiceError(f"{with_assets} episode sudah punya keyframe/video dengan rasio lain; rasio episode "
                                       "akan diganti mengikuti proyek, aset lama tidak diubah. Konfirmasi (confirm_sync)",
                                       409, {"films_with_assets": with_assets})
                changed_films = differ
                db.execute("UPDATE films SET aspect_ratio = ? WHERE workspace_id = ?", (new["aspect_ratio"], ws_id))
            elif "aspect_ratio" in new:
                raise ServiceError(f"rasio harus salah satu dari {', '.join(RATIOS)}", 422)
            cols = {k: (1 if v else 0) if k == "generate_audio" else v for k, v in new.items() if k in SETTING_FIELDS}
            if cols:
                self.st.db.update("workspaces", ws_id, {**cols, "updated_at": now()})
        return {**self.settings(ws_id), "synced_films": changed_films}

    # ---------- CRUD ----------
    def list_all(self, include_archived: bool = False) -> list[dict]:
        rows = self.st.db.all("SELECT * FROM workspaces WHERE deleted_at IS NULL AND (archived_at IS NULL OR ?) "
                              "ORDER BY (id = ?) DESC, name", (1 if include_archived else 0, DEFAULT_WS))
        return [self.public(r) for r in rows]

    def _name_taken(self, name: str, except_id: str | None = None) -> bool:
        row = self.st.db.one("SELECT id FROM workspaces WHERE name = ?", (name,))
        return bool(row and row["id"] != except_id)

    def create(self, name: str) -> dict:
        name = self._clean(name)
        with self.st._lock:
            if self._name_taken(name):
                raise ServiceError("sudah ada workspace dengan nama itu", 409)
            stamp = now()
            row = {"id": uuid.uuid4().hex, "name": name, "created_at": stamp, "updated_at": stamp}
            self.st.db.insert("workspaces", row)
        return self.public({**row, "archived_at": None})

    def rename(self, ws_id: str, name: str) -> dict:
        name = self._clean(name)
        with self.st._lock:
            self.get(ws_id)
            if self._name_taken(name, ws_id):
                raise ServiceError("sudah ada workspace dengan nama itu", 409)
            self.st.db.update("workspaces", ws_id, {"name": name, "updated_at": now()})
        return self.public(self.get(ws_id))

    def archive(self, ws_id: str, active_ws: str) -> dict:
        if ws_id == DEFAULT_WS:
            raise ServiceError("workspace Utama tidak bisa diarsipkan", 400)
        if ws_id == active_ws:
            raise ServiceError("workspace yang sedang aktif tidak bisa diarsipkan; pindah dulu", 400)
        with self.st._lock:
            self.get(ws_id)
            self.st.db.update("workspaces", ws_id, {"archived_at": now(), "updated_at": now()})
        return self.public(self.st.db.one("SELECT * FROM workspaces WHERE id = ?", (ws_id,)))

    def restore(self, ws_id: str) -> dict:
        with self.st._lock:
            row = self._get_any(ws_id)
            if not row["archived_at"]:
                raise ServiceError("workspace tidak sedang diarsipkan", 409)
            self.st.db.update("workspaces", ws_id, {"archived_at": None, "updated_at": now()})
        return self.public(self.get(ws_id))

    def delete(self, ws_id: str, active_ws: str) -> dict:
        """Hapus permanen workspace yang sudah diarsip (plan 07 revisi 1).

        Gambar dan klip hanya ditandai terhapus (barisnya tetap agar catatan biaya/batas harian utuh) dan filenya dihapus;
        karakter, film, dan referensi video dihapus sungguhan. Perubahan DB satu transaksi; file dihapus SETELAH commit."""
        st = self.st
        if ws_id == DEFAULT_WS:
            raise ServiceError("workspace Utama tidak bisa dihapus", 400)
        if ws_id == active_ws:
            raise ServiceError("workspace yang sedang aktif tidak bisa dihapus", 400)
        with st._lock:   # kunci yang sama dengan create_clip: tak ada job baru masuk selagi dicek
            row = self._get_any(ws_id)
            if not row["archived_at"]:
                raise ServiceError("arsipkan workspace dulu sebelum menghapusnya", 409)
            running = st.db.one("SELECT COUNT(*) AS n FROM clips WHERE workspace_id = ? AND deleted_at IS NULL "
                                "AND status IN ('submitted','in_progress')", (ws_id,))["n"]
            rendering = st.db.one("SELECT COUNT(*) AS n FROM films WHERE workspace_id = ? AND render_status = 'rendering'", (ws_id,))["n"]
            if running or rendering:
                raise ServiceError(f"masih ada {running} job video berjalan dan {rendering} film dirender; tunggu selesai", 409)
            counts = self._counts(ws_id)
            files = [r["path"] for r in st.db.all("SELECT path FROM images WHERE workspace_id = ? AND deleted_at IS NULL", (ws_id,))]
            for r in st.db.all("SELECT path, merged_path FROM clips WHERE workspace_id = ? AND deleted_at IS NULL", (ws_id,)):
                files += [r["path"], r["merged_path"]]
            files += [r["merged_path"] for r in st.db.all("SELECT merged_path FROM films WHERE workspace_id = ?", (ws_id,))]
            # referensi "dari klip" memakai file klip itu sendiri: hanya unggahan sendiri yang dihapus di sini
            files += [r["path"] for r in st.db.all("SELECT path FROM refs WHERE workspace_id = ? AND source_clip_id IS NULL", (ws_id,))]
            files += [r["path"] for r in st.db.all("SELECT v.path FROM voice_versions v JOIN characters c ON c.id = v.character_id "
                                                   "WHERE c.workspace_id = ?", (ws_id,))]
            stamp = now()
            with st.db.transaction() as tx:
                for t in ("scene_beats", "beat_versions"):
                    tx.execute(f"DELETE FROM {t} WHERE scene_id IN (SELECT s.id FROM scenes s JOIN films f ON f.id = s.film_id "
                               "WHERE f.workspace_id = ?)", (ws_id,))
                tx.execute("DELETE FROM voice_versions WHERE character_id IN (SELECT id FROM characters WHERE workspace_id = ?)", (ws_id,))
                tx.execute("DELETE FROM scene_cast WHERE scene_id IN (SELECT s.id FROM scenes s JOIN films f ON f.id = s.film_id "
                           "WHERE f.workspace_id = ?)", (ws_id,))
                for t in ("film_characters", "film_locations"):
                    tx.execute(f"DELETE FROM {t} WHERE film_id IN (SELECT id FROM films WHERE workspace_id = ?)", (ws_id,))
                tx.execute("DELETE FROM scenes WHERE film_id IN (SELECT id FROM films WHERE workspace_id = ?)", (ws_id,))
                tx.execute("DELETE FROM outfits WHERE character_id IN (SELECT id FROM characters WHERE workspace_id = ?)", (ws_id,))
                tx.execute("DELETE FROM locations WHERE workspace_id = ?", (ws_id,))
                tx.execute("DELETE FROM character_images WHERE character_id IN (SELECT id FROM characters WHERE workspace_id = ?)", (ws_id,))
                tx.execute("DELETE FROM characters WHERE workspace_id = ?", (ws_id,))
                tx.execute("DELETE FROM films WHERE workspace_id = ?", (ws_id,))
                tx.execute("DELETE FROM refs WHERE workspace_id = ?", (ws_id,))
                tx.execute("UPDATE images SET deleted_at = ?, path = '' WHERE workspace_id = ? AND deleted_at IS NULL", (stamp, ws_id))
                tx.execute("UPDATE clips SET deleted_at = ?, path = NULL, merged_path = NULL WHERE workspace_id = ? AND deleted_at IS NULL",
                           (stamp, ws_id))
                # tombstone: nama diganti supaya nama asli bisa dipakai lagi; salinan di workspace lain tetap punya keterangan asal
                tx.execute("UPDATE workspaces SET deleted_at = ?, updated_at = ?, name = ? WHERE id = ?",
                           (stamp, stamp, f"{row['name']} (dihapus {ws_id[:6]})", ws_id))
        for stored in files:   # setelah commit: kegagalan hanya meninggalkan file yatim, bukan data rusak
            st._unlink(stored)
        return {"deleted": counts}

    # ---------- job lintas workspace (untuk dock) ----------
    def jobs(self) -> list[dict]:
        return self.st.db.all(
            "SELECT c.*, w.name AS workspace_name FROM clips c JOIN workspaces w ON w.id = c.workspace_id "
            "WHERE c.deleted_at IS NULL AND (c.status IN ('submitted','in_progress') OR c.id IN "
            "(SELECT id FROM clips WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 10)) "
            "ORDER BY c.created_at DESC")

    # ---------- salin ----------
    @staticmethod
    def _copy_name(base: str, existing: set[str]) -> str:
        if base not in existing:
            return base
        root, n = _COPY_SUFFIX.sub("", base), 1
        cand = f"{root} (salinan)"
        while cand in existing:
            n += 1
            cand = f"{root} (salinan {n})"
        return cand

    def copy(self, source_ws: str, target_id: str, image_ids: list[str], character_ids: list[str]) -> dict:
        """Salin gambar dan karakter dari workspace sumber ke target. Atomik: gagal sebagian = tidak ada yang tersimpan."""
        st = self.st
        self.get(target_id)   # 404 bila tidak ada / diarsip
        if target_id == source_ws:
            raise ServiceError("pilih workspace tujuan yang berbeda", 400)
        image_ids, character_ids = list(dict.fromkeys(image_ids)), list(dict.fromkeys(character_ids))
        if not image_ids and not character_ids:
            raise ServiceError("tidak ada gambar atau karakter yang dipilih", 400)
        if len(image_ids) + len(character_ids) > MAX_COPY_ITEMS:
            raise ServiceError(f"maksimum {MAX_COPY_ITEMS} item per salinan", 400)
        with st._lock:
            chars = []
            for cid in character_ids:
                ch = st.get_character(cid, source_ws)
                try:
                    st.get_image(ch["source_image_id"], source_ws)
                except ServiceError as exc:
                    raise ServiceError(f"gambar sumber karakter \"{ch['name']}\" sudah dihapus; karakter tidak bisa disalin", 409) from exc
                links = []
                for link in st.character_images(cid):   # gambar yang sudah dihapus dilewati
                    if st.db.one("SELECT 1 FROM images WHERE id = ? AND workspace_id = ? AND deleted_at IS NULL",
                                 (link["image_id"], source_ws)):
                        links.append((link["image_id"], link["label"]))
                outfits = [o for o in st.db.all("SELECT * FROM outfits WHERE character_id = ? ORDER BY created_at, rowid", (cid,))
                           if not o["image_id"] or st.db.one("SELECT 1 FROM images WHERE id = ? AND workspace_id = ? AND deleted_at IS NULL",
                                                             (o["image_id"], source_ws))]   # tampilan dengan gambar terhapus dilewati
                chars.append((ch, links, outfits))
            wanted = list(dict.fromkeys([*image_ids, *(ch["source_image_id"] for ch, _, _ in chars),
                                         *(iid for _, links, _ in chars for iid, _ in links),
                                         *(o["image_id"] for _, _, outs in chars for o in outs if o["image_id"])]))
            rows = {iid: st.get_image(iid, source_ws) for iid in wanted}   # 404 bila milik workspace lain / terhapus
            created = []
            try:
                new_id, new_images = {}, []
                for iid in wanted:
                    r = rows[iid]
                    path = st.storage.save(st.storage.resolve(r["path"]).read_bytes(), ".png")
                    created.append(path)
                    new_id[iid] = uuid.uuid4().hex
                    new_images.append({"id": new_id[iid], "parent_image_id": None, "kind": r["kind"], "prompt": r["prompt"],
                                       "model": r["model"], "path": str(path), "width": r["width"], "height": r["height"],
                                       "cost": None, "estimated_cost": None,   # salinan tidak dibayar ulang
                                       "created_at": now(), "workspace_id": target_id, "origin_image_id": iid})
                names = {r["name"] for r in st.db.all("SELECT name FROM characters WHERE workspace_id = ?", (target_id,))}
                new_chars = []
                for ch, links, outs in chars:
                    name = self._copy_name(ch["name"], names)
                    names.add(name)
                    ncid = uuid.uuid4().hex
                    new_chars.append(({"id": ncid, "name": name, "description": ch["description"],
                                       "source_image_id": new_id[ch["source_image_id"]], "created_at": now(),
                                       "workspace_id": target_id, "look": ch.get("look"), "look_hash": ch.get("look_hash")}, [(ncid, new_id[iid], label) for iid, label in links],
                                      [{"id": uuid.uuid4().hex, "character_id": ncid, "name": o["name"], "description": o["description"],
                                        "image_id": new_id[o["image_id"]] if o["image_id"] else None, "created_at": now()} for o in outs]))
                active_voices = {ch["id"]: st.voices.active(ch["id"]) for ch, _, _ in chars}   # sebelum transaksi (kunci DB)
                with st.db.transaction() as tx:
                    for row in new_images:
                        tx.insert("images", row)
                    for row, links, new_outfits in new_chars:
                        tx.insert("characters", row)
                        for outfit in new_outfits:
                            tx.insert("outfits", outfit)
                        for ncid, nid, label in links:
                            tx.insert("character_images", {"character_id": ncid, "image_id": nid, "label": label})
                    for (ch, _, _), (row, _, _) in zip(chars, new_chars):   # suara aktif ikut disalin (grill 18 no. 9)
                        created += st.voices.copy_active(tx, active_voices[ch["id"]], row["id"])
            except BaseException:
                for p in created:
                    p.unlink(missing_ok=True)
                raise
        return {"workspace_id": target_id,
                "images": [{"from": i["origin_image_id"], "to": i["id"]} for i in new_images],
                "characters": [{"from": ch["id"], "to": row["id"], "name": row["name"]}
                               for (ch, _, _), (row, _, _) in zip(chars, new_chars)]}
