"""Beat adegan (plan 18 fase C): pembagian waktu adegan jadi ketukan dengan rentang detik, aksi, kamera, pemeran, dan dialog.

`clean` murni (tanpa DB) supaya aturannya teruji sendiri. `Beats` menyimpan; setiap penggantian memotret susunan lama
ke `beat_versions` (satu transaksi) sehingga bisa dikembalikan. Tidak ada batas jumlah beat dari aturan kita (plan 18
Revisi 2); SAFE_MAX hanya penjaga teknis terhadap payload yang tidak masuk akal.
"""
from __future__ import annotations   # metode bernama `list` menutupi builtin di dalam badan kelas

import json
import math
import uuid

from . import beatsai, textai
from .db import now
from .service import DEFAULT_WS, ServiceError

MIN_BEAT = 1.0          # detik; beat lebih pendek dari ini tidak punya gambar yang bermakna
TOL = 0.05              # toleransi pembulatan sambungan antar beat
ACTION_MAX, CAMERA_MAX, DIALOGUE_MAX = 300, 120, 300
SAFE_MAX = 200
VERSIONS_MAX = 50
SIZES = ("WS", "MS", "MCU", "CU", "ECU")   # ukuran shot (format prompt Seedance, plan 18 Revisi 4)
LENSES = ("24", "35", "50", "85")           # mm
MAX_SHOT = 3.0                              # format menganjurkan shot 1-3 dtk; lebih dari ini hanya peringatan
WORDS_PER_SECOND = 3.0   # di atas ini dialog dianggap terlalu padat untuk rentang beat (peringatan, bukan galat)


def _num(value, what: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ServiceError(f"{what} harus angka", 422) from None
    if not math.isfinite(v):
        raise ServiceError(f"{what} harus angka", 422)
    return round(v, 1)


def _text(value, what: str, limit: int) -> str:
    value = (value or "").strip()
    if len(value) > limit:
        raise ServiceError(f"{what} maksimal {limit} karakter", 422)
    return value


def clean(items: list[dict], cast_ids: set[str], planned: float | None = None, strict: bool = True) -> tuple[list[dict], list[str]]:
    """Validasi + normalisasi. `strict=False` (pemulihan versi lama) membuang id pemeran yang sudah tidak ada, dengan peringatan."""
    if not isinstance(items, list) or not items:
        raise ServiceError("minimal satu beat", 422)
    if len(items) > SAFE_MAX:
        raise ServiceError(f"terlalu banyak beat (penjaga teknis {SAFE_MAX})", 422)
    out, warnings, prev_end = [], [], 0.0
    for n, raw in enumerate(items, 1):
        label = f"beat {n}"
        start, end = _num(raw.get("start"), f"{label}: start"), _num(raw.get("end"), f"{label}: end")
        if n == 1 and abs(start) > TOL:
            raise ServiceError(f"{label}: beat pertama harus mulai di 0", 422)
        if n > 1 and abs(start - prev_end) > TOL:
            raise ServiceError(f"{label}: harus mulai di {prev_end:g} dtk (sambung dengan beat sebelumnya, tanpa celah atau tumpang tindih)", 422)
        start = 0.0 if n == 1 else prev_end
        if end - start < MIN_BEAT - 1e-9:
            raise ServiceError(f"{label}: panjang minimal {MIN_BEAT:g} dtk", 422)
        cast = list(dict.fromkeys(raw.get("cast") or []))
        unknown = [c for c in cast if c not in cast_ids]
        if unknown:
            if strict:
                raise ServiceError(f"{label}: pemeran bukan bagian dari adegan", 422)
            cast = [c for c in cast if c in cast_ids]
            warnings.append(f"{label}: pemeran yang sudah tidak ada dilepas")
        dialogue = []
        for d in raw.get("dialogue") or []:
            text = _text(d.get("text"), f"{label}: dialog", DIALOGUE_MAX)
            if not text:
                continue
            if d.get("character_id") not in cast_ids:
                if strict:
                    raise ServiceError(f"{label}: penutur dialog bukan bagian dari adegan", 422)
                warnings.append(f"{label}: dialog penutur yang sudah tidak ada dibuang")
                continue
            dialogue.append({"character_id": d["character_id"], "text": text})
        size = str(raw.get("size") or "").strip().upper() or None
        lens = str(raw.get("lens") or "").strip().lower().removesuffix("mm").strip() or None
        if size and size not in SIZES:
            raise ServiceError(f"{label}: ukuran shot harus salah satu dari {', '.join(SIZES)}", 422)
        if lens and lens not in LENSES:
            raise ServiceError(f"{label}: lensa harus salah satu dari {', '.join(L + 'mm' for L in LENSES)}", 422)
        if end - start > MAX_SHOT + 1e-9:
            warnings.append(f"{label}: {end - start:g} dtk; format menganjurkan shot 1-{MAX_SHOT:g} dtk, pertimbangkan dipecah")
        words = sum(len(d["text"].split()) for d in dialogue)
        if words and words / (end - start) > WORDS_PER_SECOND:
            warnings.append(f"{label}: dialog {words} kata untuk {end - start:g} dtk terlalu padat")
        out.append({"id": raw.get("id") or uuid.uuid4().hex, "start": start, "end": end,
                    "action": _text(raw.get("action"), f"{label}: aksi", ACTION_MAX),
                    "camera": _text(raw.get("camera"), f"{label}: kamera", CAMERA_MAX),
                    "size": size, "lens": lens, "cast": cast, "dialogue": dialogue, "image_id": raw.get("image_id")})
        prev_end = end
    if len({b["id"] for b in out}) != len(out):
        raise ServiceError("id beat duplikat", 422)
    for a, b, c in zip(out, out[1:], out[2:]):
        if a["size"] and (a["size"], a["lens"]) == (b["size"], b["lens"]) == (c["size"], c["lens"]):
            warnings.append("tiga shot berturut-turut memakai ukuran dan lensa sama; variasikan agar terasa sinematik")
            break
    if planned and abs(prev_end - planned) > TOL:
        warnings.append(f"total beat {prev_end:g} dtk, durasi adegan {planned:g} dtk")
    return out, warnings


class Beats:
    def __init__(self, studio):
        self.st = studio

    def _public(self, row: dict, cast_ids: set[str]) -> dict:
        cast, dialogue = json.loads(row["cast"]), json.loads(row["dialogue"])
        broken = any(c not in cast_ids for c in cast) or any(d["character_id"] not in cast_ids for d in dialogue)
        return {"id": row["id"], "start": row["start"], "end": row["end"], "action": row["action"], "camera": row["camera"],
                "size": row["size"], "lens": row["lens"], "cast": cast, "dialogue": dialogue, "image_id": row["image_id"], "broken": broken}

    def _cast_ids(self, scene_id: str) -> set[str]:
        return {r["character_id"] for r in self.st.db.all("SELECT character_id FROM scene_cast WHERE scene_id = ?", (scene_id,))}

    def list(self, scene_id: str, ws: str = DEFAULT_WS) -> dict:
        scene = self.st.scenes._scene(scene_id, ws)
        cast_ids = self._cast_ids(scene_id)
        rows = self.st.db.all("SELECT * FROM scene_beats WHERE scene_id = ? ORDER BY position", (scene_id,))
        beats = [self._public(r, cast_ids) for r in rows]
        warnings = [f"beat {n} memakai pemeran yang sudah dilepas dari adegan" for n, b in enumerate(beats, 1) if b["broken"]]
        planned = scene["planned_seconds"]
        if beats and planned and abs(beats[-1]["end"] - planned) > TOL:
            warnings.append(f"total beat {beats[-1]['end']:g} dtk, durasi adegan {planned:g} dtk")
        return {"beats": beats, "planned_seconds": planned, "warnings": warnings}

    def _alive_image(self, image_id: str | None, ws: str) -> str | None:
        if not image_id:
            return None
        row = self.st.db.one("SELECT 1 FROM images WHERE id = ? AND workspace_id = ? AND deleted_at IS NULL", (image_id, ws))
        return image_id if row else None

    def _write(self, scene: dict, ws: str, items: list[dict], note: str, strict: bool, trusted: bool = False) -> list[str]:
        """Ganti seluruh beat adegan; susunan lama dipotret dulu. `trusted` (pemulihan versi): gambar dari snapshot dipertahankan
        bila masih ada; selain itu gambar hanya diwarisi dari beat lama dengan id yang sama dan id baru buatan klien diabaikan."""
        db = self.st.db
        cast_ids = self._cast_ids(scene["id"])
        cleaned, warnings = clean(items, cast_ids, scene["planned_seconds"], strict)
        old = db.all("SELECT * FROM scene_beats WHERE scene_id = ? ORDER BY position", (scene["id"],))
        keep = {b["id"]: b for b in old}
        alive = {i for i in {*(b["image_id"] for b in old), *(b["image_id"] for b in cleaned)} if self._alive_image(i, ws)}   # sebelum transaksi (kunci DB)
        stamp = now()
        with db.transaction() as tx:
            if old:
                snap = [{k: (json.loads(b[k]) if k in ("cast", "dialogue") else b[k]) for k in
                         ("id", "start", "end", "action", "camera", "size", "lens", "cast", "dialogue", "image_id")} for b in old]
                tx.insert("beat_versions", {"id": uuid.uuid4().hex, "scene_id": scene["id"], "beats": json.dumps(snap),
                                            "note": note, "created_at": stamp})
                tx.execute("DELETE FROM beat_versions WHERE scene_id = ? AND id NOT IN (SELECT id FROM beat_versions "
                           "WHERE scene_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?)", (scene["id"], scene["id"], VERSIONS_MAX))
            tx.execute("DELETE FROM scene_beats WHERE scene_id = ?", (scene["id"],))
            tx.execute("UPDATE scenes SET prompt = NULL WHERE id = ?", (scene["id"],))   # prompt adegan dirender ulang dari beat baru
            for pos, b in enumerate(cleaned):
                bid, created = b["id"], stamp
                if bid in keep:
                    image_id, created = keep[bid]["image_id"], keep[bid]["created_at"]
                    if trusted:
                        image_id = b["image_id"]
                else:
                    image_id = b["image_id"] if trusted else None
                    if not trusted or tx.one("SELECT 1 FROM scene_beats WHERE id = ?", (bid,)):
                        bid = uuid.uuid4().hex   # id buatan klien tidak dipercaya; id snapshot yang bentrok diganti
                tx.insert("scene_beats", {"id": bid, "scene_id": scene["id"], "position": pos, "start": b["start"], "end": b["end"],
                                          "action": b["action"], "camera": b["camera"], "size": b["size"], "lens": b["lens"], "cast": json.dumps(b["cast"]),
                                          "dialogue": json.dumps(b["dialogue"]), "image_id": image_id if image_id in alive else None,
                                          "created_at": created, "updated_at": stamp})
        return warnings

    def replace(self, scene_id: str, items: list[dict], note: str = "", ws: str = DEFAULT_WS) -> dict:
        with self.st._lock:
            scene = self.st.scenes._scene(scene_id, ws)
            self.st.scenes._editable(scene["film_id"])
            warnings = self._write(scene, ws, items, _text(note, "catatan", 200), True)
        return {**self.list(scene_id, ws), "warnings_save": warnings}

    # ---------- AI (plan 18 Revisi 4): draf shot sesuai format Seedance; tidak disimpan sampai user menyimpan ----------
    AI_MAX_TOKENS = 4000

    def _ai_context(self, scene_id: str, ws: str) -> dict:
        scene = self.st.scenes._scene(scene_id, ws)
        project = self.st.workspaces.get(ws)
        loc = self.st.db.one("SELECT name, description FROM locations WHERE id = ?", (scene["location_id"],)) if scene["location_id"] else None
        rows = self.st.db.all(
            "SELECT sc.character_id, sc.action, c.name, c.description, o.name AS outfit_name, o.description AS outfit_desc FROM scene_cast sc "
            "JOIN characters c ON c.id = sc.character_id LEFT JOIN outfits o ON o.id = sc.outfit_id WHERE sc.scene_id = ? ORDER BY sc.position", (scene_id,))
        return {"scene": scene, "duration": float(scene["planned_seconds"] or 8), "genre": project["genre"] or "", "style": project["style"],
                "location": loc, "time_of_day": scene["time_of_day"], "camera": scene["camera"], "dialogue": scene["dialogue"],
                "extra": scene["extra_prompt"],
                "cast": [{"character_id": r["character_id"], "name": r["name"], "description": r["description"], "action": r["action"],
                          "wardrobe": r["outfit_desc"] or r["outfit_name"] or ""} for r in rows]}

    def ai_estimate(self, scene_id: str, ws: str = DEFAULT_WS, model: str | None = None):
        ctx = self._ai_context(scene_id, ws)
        return textai.estimate(self.st, beatsai.SYSTEM, beatsai.user_prompt(ctx), self.AI_MAX_TOKENS, model=model)

    def generate_ai(self, scene_id: str, ws: str = DEFAULT_WS, confirmed_cost: float | None = None,
                    accept_unknown_cost: bool = False, model: str | None = None) -> dict:
        """AI membuat shot. Hasil DRAF yang sudah divalidasi `clean`; tidak disimpan. Pelanggaran aturan: satu kali ulang dengan pesan
        galatnya (dibayar, dengan konfirmasi biaya yang sama), lalu ditolak 502; tidak ada perbaikan diam-diam."""
        with self.st._lock:
            ctx = self._ai_context(scene_id, ws)
            self.st.scenes._editable(ctx["scene"]["film_id"])
            if not ctx["cast"] and not ctx["dialogue"].strip() and not ctx["extra"].strip():
                raise ServiceError("adegan belum punya pemeran, dialog, atau arahan; isi dulu agar AI punya bahan", 422)
            system, user = beatsai.SYSTEM, beatsai.user_prompt(ctx)
            est = textai.estimate(self.st, system, user, self.AI_MAX_TOKENS, model=model)
            cast_ids = {c["character_id"] for c in ctx["cast"]}
            total, last_error = 0.0, ""
            for attempt in (1, 2):
                raw, cost = textai.ask(self.st, "scene_beats", system, user + (f"\n\nYour previous answer was rejected: {last_error}. Fix it and answer again."
                                                                              if last_error else ""),
                                       self.AI_MAX_TOKENS, est, ws, confirmed_cost, accept_unknown_cost, scene_id=scene_id, model=model)
                total += cost or 0.0
                try:
                    items = beatsai.shots_to_beats(raw)
                    beats, warnings = clean(items, cast_ids, ctx["duration"])
                    if abs(beats[-1]["end"] - ctx["duration"]) > TOL:
                        raise ServiceError(f"shot terakhir harus berakhir tepat di {ctx['duration']:g} dtk", 422)
                    if any(b["end"] - b["start"] > MAX_SHOT + 1e-9 for b in beats):
                        raise ServiceError(f"setiap shot maksimal {MAX_SHOT:g} dtk", 422)
                    for b in beats:   # draf: id baru, tanpa gambar
                        b["image_id"] = None
                    return {"beats": beats, "warnings": warnings, "cost": total or None, "estimated_cost": est.high, "attempts": attempt}
                except (ValueError, TypeError, KeyError, ServiceError) as exc:
                    last_error = str(exc)
            raise ServiceError(f"AI menghasilkan shot yang tidak sesuai aturan format ({last_error}); coba lagi atau pilih model lain", 502)

    # ---------- AI: ubah adegan yang sudah ada (plan 18 Revisi 6); draf, tidak disimpan ----------
    def _revise_ctx(self, scene_id: str, ws: str) -> tuple[dict, list[dict]]:
        ctx = self._ai_context(scene_id, ws)
        cast_ids = {c["character_id"] for c in ctx["cast"]}
        current = self.list(scene_id, ws)["beats"]
        if not current:
            raise ServiceError("adegan ini belum punya beat; buat dulu (bagi rata atau 'Buat shot dengan AI') lalu ubah", 422)
        if any(b["broken"] for b in current):
            raise ServiceError("beat memakai pemeran yang sudah dilepas dari adegan; perbaiki dulu", 422)
        return {**ctx, "cast_ids": cast_ids}, current

    def revise_estimate(self, scene_id: str, ws: str = DEFAULT_WS, model: str | None = None):
        """Estimasi memakai instruksi sepanjang batas (INSTRUCTION_MAX) supaya konstan dan sama dengan yang dihitung saat generate."""
        ctx, current = self._revise_ctx(scene_id, ws)
        return textai.estimate(self.st, beatsai.REVISE_SYSTEM, beatsai.revise_prompt(ctx, current, "x" * beatsai.INSTRUCTION_MAX),
                               self.AI_MAX_TOKENS, model=model)

    def revise_ai(self, scene_id: str, instruction: str, ws: str = DEFAULT_WS, confirmed_cost: float | None = None,
                  accept_unknown_cost: bool = False, model: str | None = None) -> dict:
        instruction = (instruction or "").strip()
        if not instruction:
            raise ServiceError("tulis dulu apa yang ingin diubah", 422)
        if len(instruction) > beatsai.INSTRUCTION_MAX:
            raise ServiceError(f"instruksi maksimal {beatsai.INSTRUCTION_MAX} karakter", 422)
        with self.st._lock:
            ctx, current = self._revise_ctx(scene_id, ws)
            self.st.scenes._editable(ctx["scene"]["film_id"])
            system, user = beatsai.REVISE_SYSTEM, beatsai.revise_prompt(ctx, current, instruction)
            est = textai.estimate(self.st, system, beatsai.revise_prompt(ctx, current, "x" * beatsai.INSTRUCTION_MAX), self.AI_MAX_TOKENS, model=model)
            old_total = current[-1]["end"]
            total, last_error = 0.0, ""
            for attempt in (1, 2):
                raw, cost = textai.ask(self.st, "scene_revise", system, user + (f"\n\nYour previous answer was rejected: {last_error}. Fix it and answer again."
                                                                              if last_error else ""),
                                       self.AI_MAX_TOKENS, est, ws, confirmed_cost, accept_unknown_cost, scene_id=scene_id, model=model)
                total += cost or 0.0
                try:
                    items, keeps, meta = beatsai.revision_to_beats(raw)
                    target = meta["total_seconds"] if isinstance(meta["total_seconds"], (int, float)) and not isinstance(meta["total_seconds"], bool) else old_total
                    if not 1 <= target <= 15:
                        raise ServiceError("total_seconds harus 1 sampai 15", 422)
                    beats, warnings = clean(items, ctx["cast_ids"], target)
                    if abs(beats[-1]["end"] - target) > TOL:
                        raise ServiceError(f"shot terakhir harus berakhir tepat di {target:g} dtk", 422)
                    if any(b["end"] - b["start"] > MAX_SHOT + 1e-9 for b in beats):
                        raise ServiceError(f"setiap shot maksimal {MAX_SHOT:g} dtk", 422)
                    used: set[int] = set()
                    for b, k in zip(beats, keeps):   # hanya `keep` yang sah (bulat 1..N, sekali pakai) mewarisi id dan gambar lama
                        old = current[k - 1] if isinstance(k, int) and not isinstance(k, bool) and 1 <= k <= len(current) and k not in used else None
                        if old:
                            used.add(k)
                            b["id"], b["image_id"] = old["id"], old["image_id"]
                            same = all(b[f] == old[f] for f in ("start", "end", "action", "camera", "size", "lens", "cast", "dialogue"))
                        else:
                            b["image_id"], same = None, False
                        b["from"], b["changed"] = (k if old else None), not same
                    mood = meta["mood"] if isinstance(meta["mood"], str) else ctx["extra"]
                    tod = meta["time_of_day"] if isinstance(meta["time_of_day"], str) else ctx["time_of_day"]
                    return {"beats": beats, "warnings": warnings, "total_seconds": target, "previous_seconds": old_total,
                            "mood": mood.strip()[:500], "time_of_day": tod.strip()[:60],
                            "mood_changed": mood.strip() != (ctx["extra"] or "").strip(), "time_changed": tod.strip() != (ctx["time_of_day"] or "").strip(),
                            "cost": total or None, "estimated_cost": est.high, "attempts": attempt}
                except (ValueError, TypeError, KeyError, ServiceError) as exc:
                    last_error = str(exc)
            raise ServiceError(f"AI menghasilkan revisi yang tidak sesuai aturan ({last_error}); coba lagi, perjelas instruksi, atau pilih model lain", 502)

    def versions(self, scene_id: str, ws: str = DEFAULT_WS) -> list[dict]:
        self.st.scenes._scene(scene_id, ws)
        return [{"id": r["id"], "note": r["note"], "created_at": r["created_at"], "count": len(json.loads(r["beats"])),
                 "seconds": json.loads(r["beats"])[-1]["end"] if json.loads(r["beats"]) else 0}
                for r in self.st.db.all("SELECT * FROM beat_versions WHERE scene_id = ? ORDER BY created_at DESC, rowid DESC", (scene_id,))]

    def restore(self, scene_id: str, version_id: str, ws: str = DEFAULT_WS) -> dict:
        with self.st._lock:
            scene = self.st.scenes._scene(scene_id, ws)
            self.st.scenes._editable(scene["film_id"])
            ver = self.st.db.one("SELECT * FROM beat_versions WHERE id = ? AND scene_id = ?", (version_id, scene_id))
            if not ver:
                raise ServiceError("versi beat tidak ditemukan", 404)
            items = json.loads(ver["beats"])
            warnings = self._write(scene, ws, items, "sebelum pemulihan versi", False, trusted=True)
        return {**self.list(scene_id, ws), "warnings_save": warnings}
