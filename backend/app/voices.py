"""Suara karakter (plan 18 fase B): sampel suara unggahan dan/atau deskripsi suara, berversi per karakter.

Satu versi aktif per karakter (`characters.voice_id`) yang dipakai saat generate video. Mengganti suara membuat versi baru;
versi lama tetap ada dan bisa diaktifkan lagi. Tidak ada kloning suara orang lain: unggahan butuh persetujuan eksplisit
(`consent`) bahwa suara itu milik user atau dipakai dengan izin pemiliknya.
"""
from __future__ import annotations   # metode bernama `list` menutupi builtin di dalam badan kelas

import uuid
from pathlib import Path

from . import media
from .db import now
from .service import DEFAULT_WS, ServiceError

MIN_SECONDS, MAX_SECONDS = 2.0, 15.0   # batas akhir ditentukan spike plan 18 (fase 0)
DESC_MAX, NOTE_MAX = 300, 200


class Voices:
    def __init__(self, studio):
        self.st = studio

    def _public(self, row: dict, active: str | None) -> dict:
        return {"id": row["id"], "character_id": row["character_id"], "description": row["description"],
                "has_audio": bool(row["path"]), "duration": row["duration"], "source": row["source"],
                "consent": bool(row["consent"]), "revision_note": row["revision_note"], "created_at": row["created_at"],
                "active": row["id"] == active}

    def _version(self, voice_id: str, ws: str | None) -> dict:
        sql = ("SELECT v.* FROM voice_versions v JOIN characters c ON c.id = v.character_id WHERE v.id = ?"
               + (" AND c.workspace_id = ?" if ws is not None else ""))
        row = self.st.db.one(sql, (voice_id, ws) if ws is not None else (voice_id,))
        if not row:
            raise ServiceError("suara tidak ditemukan", 404)
        return row

    def list(self, character_id: str, ws: str = DEFAULT_WS) -> dict:
        ch = self.st.get_character(character_id, ws)
        rows = self.st.db.all("SELECT * FROM voice_versions WHERE character_id = ? ORDER BY created_at DESC, rowid DESC", (character_id,))
        return {"active": ch.get("voice_id"), "versions": [self._public(r, ch.get("voice_id")) for r in rows]}

    def active(self, character_id: str) -> dict | None:
        """Versi aktif (baris DB lengkap, termasuk path) untuk perakit request video; None bila belum ada suara."""
        ch = self.st.db.one("SELECT voice_id FROM characters WHERE id = ?", (character_id,))
        return self.st.db.one("SELECT * FROM voice_versions WHERE id = ?", (ch["voice_id"],)) if ch and ch["voice_id"] else None

    def add(self, character_id: str, description: str, upload: Path | None, consent: bool, note: str = "",
            ws: str = DEFAULT_WS) -> dict:
        """Versi suara baru (langsung aktif). `upload` = berkas sementara; tanpa berkas harus ada deskripsi."""
        description, note = (description or "").strip(), (note or "").strip()
        if len(description) > DESC_MAX:
            raise ServiceError(f"deskripsi suara maksimal {DESC_MAX} karakter", 422)
        if len(note) > NOTE_MAX:
            raise ServiceError(f"catatan maksimal {NOTE_MAX} karakter", 422)
        if upload is None and not description:
            raise ServiceError("isi deskripsi suara atau unggah sampel suara", 422)
        if upload is not None and not consent:
            raise ServiceError("centang persetujuan: suara ini milik Anda atau dipakai dengan izin pemiliknya", 422)
        with self.st._lock:
            self.st.get_character(character_id, ws)
            path, duration = None, None
            if upload is not None:
                out = self.st.storage.new_path(".m4a")
                try:
                    duration = media.prepare_voice(upload, out, MAX_SECONDS)
                except media.MediaError as exc:
                    out.unlink(missing_ok=True)
                    raise ServiceError(f"audio tidak valid: {exc}", 415) from exc
                if duration < MIN_SECONDS - 0.05:
                    out.unlink(missing_ok=True)
                    raise ServiceError(f"sampel suara minimal {MIN_SECONDS:g} detik (terbaca {duration:.1f} dtk)", 422)
                path = str(out)
            row = {"id": uuid.uuid4().hex, "character_id": character_id, "description": description, "path": path,
                   "duration": duration, "source": "upload" if upload is not None else "text", "consent": 1 if consent else 0,
                   "revision_note": note or None, "created_at": now()}
            with self.st.db.transaction() as tx:
                tx.insert("voice_versions", row)
                tx.execute("UPDATE characters SET voice_id = ? WHERE id = ?", (row["id"], character_id))
        return self._public(row, row["id"])

    def activate(self, voice_id: str, ws: str = DEFAULT_WS) -> dict:
        with self.st._lock:
            v = self._version(voice_id, ws)
            self.st.db.execute("UPDATE characters SET voice_id = ? WHERE id = ?", (voice_id, v["character_id"]))
        return self._public(v, voice_id)

    def delete(self, voice_id: str, ws: str = DEFAULT_WS) -> None:
        with self.st._lock:
            v = self._version(voice_id, ws)
            with self.st.db.transaction() as tx:
                tx.execute("DELETE FROM voice_versions WHERE id = ?", (voice_id,))
                ch = tx.one("SELECT voice_id FROM characters WHERE id = ?", (v["character_id"],))
                if ch and ch["voice_id"] == voice_id:   # yang aktif dihapus: pindah ke versi terbaru yang tersisa
                    nxt = tx.one("SELECT id FROM voice_versions WHERE character_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                                 (v["character_id"],))
                    tx.execute("UPDATE characters SET voice_id = ? WHERE id = ?", (nxt["id"] if nxt else None, v["character_id"]))
        self.st._unlink(v["path"])

    def file_path(self, voice_id: str) -> Path:
        v = self._version(voice_id, None)   # berkas hanya-baca: tanpa batas workspace, seperti gambar dan klip
        if not v["path"]:
            raise ServiceError("versi suara ini tidak punya sampel audio", 404)
        return self.st.storage.resolve(v["path"])

    def copy_active(self, tx, v: dict | None, new_char_id: str) -> list[Path]:
        """Salin versi suara `v` (baris `active()` yang diambil SEBELUM transaksi dibuka: kunci DB tidak reentrant) ke karakter
        hasil salinan workspace (grill 18 no. 9). Mengembalikan berkas baru (untuk rollback)."""
        if not v:
            return []
        path, created = None, []
        if v["path"] and Path(v["path"]).is_file():
            path = self.st.storage.save(Path(v["path"]).read_bytes(), ".m4a")
            created.append(path)
        new_id = uuid.uuid4().hex
        tx.insert("voice_versions", {**{k: v[k] for k in ("description", "duration", "source", "consent", "revision_note")},
                                     "id": new_id, "character_id": new_char_id, "path": str(path) if path else None, "created_at": now()})
        tx.execute("UPDATE characters SET voice_id = ? WHERE id = ?", (new_id, new_char_id))
        return created
