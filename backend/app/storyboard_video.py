"""Generate video adegan Storyboard v2 dengan Seedance 2.0 (plan 18 fase D).

`plan` merakit semua masukan (pengaturan proyek, beat, pemeran, latar, suara) lewat `seedance_request.build` dan menjadi SATU sumber untuk
pratinjau, estimasi, dan pengiriman. Batas biaya per job/harian tidak memblokir jalur ini (plan 18 Revisi 2); konfirmasi biaya tetap wajib.
Satu adegan = satu request <= 15 detik. Adegan lebih panjang ditolak dengan saran membagi adegan (segmen otomatis belum dibangun).
"""
from __future__ import annotations

import json
import math
import uuid
from pathlib import Path

from . import media, pricing, seedance_request
from .db import now
from .motion import MODERATION_HINT
from .openrouter import OpenRouterError
from .publicmedia import NoPublicMedia, PublicMediaError
from .service import DEFAULT_WS, ServiceError
from .workspaces import MODEL_CAPS, V2_VIDEO_MODELS

MIN_SECONDS, MAX_SECONDS = 4, 15   # batas durasi satu video Seedance
DEFAULT_SECONDS = 8                # adegan tanpa beat dan tanpa durasi rencana
PROMPT_MAX = 4000


class StoryboardVideo:
    def __init__(self, studio):
        self.st = studio

    # ---------- bahan ----------
    def _cast(self, scene_id: str, ws: str) -> tuple[list[dict], list[str]]:
        warnings, out = [], []
        rows = self.st.db.all(
            "SELECT sc.character_id, sc.outfit_id, sc.action, c.name, c.description, c.source_image_id FROM scene_cast sc "
            "JOIN characters c ON c.id = sc.character_id WHERE sc.scene_id = ? ORDER BY sc.position", (scene_id,))
        for r in rows:
            outfit = self.st.db.one("SELECT name, description, image_id FROM outfits WHERE id = ?", (r["outfit_id"],)) if r["outfit_id"] else None
            image_id = (outfit or {}).get("image_id") or r["source_image_id"]
            try:
                self.st.get_image(image_id, ws)
            except ServiceError:
                warnings.append(f"gambar karakter {r['name']} sudah dihapus; dikirim tanpa gambarnya")
                image_id = None
            out.append({"character_id": r["character_id"], "name": r["name"], "description": r["description"],
                        "action": r["action"], "image_id": image_id,
                        "wardrobe": ((outfit or {}).get("description") or (outfit or {}).get("name") or "")})
        return out, warnings

    def _beats(self, scene_id: str, ws: str) -> list[dict]:
        out = []
        for r in self.st.db.all("SELECT * FROM scene_beats WHERE scene_id = ? ORDER BY position", (scene_id,)):
            image_id = r["image_id"]
            if image_id and not self.st.db.one("SELECT 1 FROM images WHERE id = ? AND workspace_id = ? AND deleted_at IS NULL", (image_id, ws)):
                image_id = None
            out.append({"start": r["start"], "end": r["end"], "action": r["action"], "camera": r["camera"],
                        "size": r["size"], "lens": r["lens"], "cast": json.loads(r["cast"]), "dialogue": json.loads(r["dialogue"]), "image_id": image_id})
        return out

    def _voices(self, cast: list[dict]) -> dict[str, dict]:
        out = {}
        for c in cast:
            v = self.st.voices.active(c["character_id"])
            if v:
                has = bool(v["path"]) and Path(v["path"]).is_file()
                out[c["character_id"]] = {"description": v["description"], "has_audio": has, "voice_id": v["id"], "path": v["path"] if has else None}
        return out

    # ---------- rencana (satu sumber untuk pratinjau, estimasi, kirim) ----------
    def start_info(self, scene: dict, ws: str, source_id: str | None = None) -> dict:
        """Frame awal dari frame akhir video adegan lain di episode yang sama (plan 18 Revisi 11):
        {ok, reason, scene_number, clip_id, path}. `source_id` kosong = adegan yang dipilih pada `scene`."""
        source_id = source_id or scene.get("start_from_scene_id")
        src = self.st.db.one("SELECT * FROM scenes WHERE id = ? AND film_id = ?", (source_id, scene["film_id"])) if source_id else None
        if not src:
            return {"ok": False, "reason": "adegan sumber tidak ada di episode ini", "scene_number": None, "clip_id": None, "path": None}
        number = src["position"] + 1
        if not src["clip_id"]:
            return {"ok": False, "reason": f"adegan {number} belum punya video; buat atau pilih videonya dulu", "scene_number": number, "clip_id": None, "path": None}
        clip = self.st.db.one("SELECT * FROM clips WHERE id = ? AND deleted_at IS NULL AND workspace_id = ?", (src["clip_id"], ws))
        if not clip or clip["status"] != "completed" or not clip["path"] or not self.st.storage.resolve(clip["path"]).is_file():
            return {"ok": False, "reason": f"video adegan {number} belum selesai atau berkasnya hilang", "scene_number": number, "clip_id": None, "path": None}
        return {"ok": True, "reason": None, "scene_number": number, "clip_id": clip["id"], "path": clip["path"]}

    def start_candidates(self, scene: dict, ws: str) -> list[dict]:
        """Semua adegan lain di episode ini sebagai pilihan sumber frame awal, lengkap dengan alasan bila belum bisa."""
        out = []
        for r in self.st.db.all("SELECT id, position FROM scenes WHERE film_id = ? AND id != ? ORDER BY position", (scene["film_id"], scene["id"])):
            i = self.start_info(scene, ws, r["id"])
            out.append({"id": r["id"], "number": r["position"] + 1, "ok": i["ok"], "reason": i["reason"]})
        return out

    def plan(self, scene_id: str, ws: str = DEFAULT_WS, *, use_audio: bool = True, use_previs: bool = False, strict: bool = True) -> dict:
        st = self.st
        scene = st.scenes._scene(scene_id, ws)
        film = st.films._row(scene["film_id"], ws)
        project = st.workspaces.get(ws)
        model = project["video_model"]
        if model not in V2_VIDEO_MODELS:
            raise ServiceError("model video proyek bukan Seedance 2.0 atau HeyGen Video 1; pilih di pengaturan proyek", 422)
        info = next((m for m in st.video_models() if m.get("id") == model), None)
        if info is None:
            raise ServiceError(f"model {model} tidak tersedia di OpenRouter saat ini", 422)

        caps = MODEL_CAPS[model]
        if use_previs and not caps["previs"]:
            raise ServiceError(f"{caps['label']} tidak mendukung previs 3D; pakai model Seedance atau matikan previs", 422)
        beats = self._beats(scene_id, ws)
        cast, warnings = self._cast(scene_id, ws)
        loc = st.db.one("SELECT name, description, image_id FROM locations WHERE id = ?", (scene["location_id"],)) if scene["location_id"] else None
        if loc and loc["image_id"]:
            try:
                st.get_image(loc["image_id"], ws)
            except ServiceError:
                warnings.append(f"gambar latar {loc['name']} sudah dihapus; dikirim tanpa gambarnya")
                loc = {**loc, "image_id": None}
        if not beats and not cast and not (loc and loc["image_id"]):
            raise ServiceError("adegan butuh minimal satu beat, pemeran, atau latar bergambar", 422)

        total = beats[-1]["end"] if beats else float(scene["planned_seconds"] or DEFAULT_SECONDS)
        duration = math.ceil(total - 1e-9)
        if duration > MAX_SECONDS:
            raise ServiceError(f"adegan ini {total:g} dtk, melebihi batas {MAX_SECONDS} dtk untuk satu video {caps['label']}; "
                               "bagi menjadi beberapa adegan (masing-masing sampai 15 dtk)", 422, {"code": "scene_too_long", "seconds": total})
        if duration < caps["min_seconds"]:
            warnings.append(f"adegan {total:g} dtk; {caps['label']} minimal {caps['min_seconds']} dtk, durasi video dibulatkan")
            duration = caps["min_seconds"]

        resolution, ratio = project["video_resolution"], project["aspect_ratio"]
        audio = bool(project["generate_audio"]) and info.get("generate_audio") is not False
        st.motion._validate_reference_params(info, duration, resolution, ratio, audio)

        start = None
        if scene["start_from_scene_id"]:
            info_s = self.start_info(scene, ws)
            if info_s["ok"] and use_previs:
                raise ServiceError("previs 3D tidak bisa digabung dengan frame awal (previs butuh referensi)", 422)
            if info_s["ok"]:
                start = info_s
            elif strict:
                raise ServiceError(f"frame awal dari adegan sumber tidak tersedia: {info_s['reason']}", 422)
            else:
                warnings.append(f"frame awal dari adegan sumber tidak tersedia ({info_s['reason']}); dikirim tanpa frame awal")

        previs = None
        if use_previs and not start:
            if not scene["previs_ref_id"]:
                raise ServiceError("adegan ini belum punya previs 3D", 422)
            previs = st.motion.get_ref(scene["previs_ref_id"], ws)
            st.motion._check_ref(previs, "reference")

        fallback = "; ".join(f"{c['name']}: {c['action']}" for c in cast if c["action"]) or (scene["extra_prompt"] or "")
        built = seedance_request.build(beats=beats, cast=cast, location=loc, voices=self._voices(cast), style=project["style"], genre=project["genre"] or "", mood=scene["extra_prompt"] or "",
                                       fallback_action=fallback, use_audio=use_audio and not start and caps["audio_refs"], previs=bool(previs),
                                       max_images=caps["max_images"])
        # Prompt adegan (plan 18 Revisi 8) adalah SATU-SATUNYA prompt: nama → @image_N sesuai referensi aktual; build() hanya memberi referensi + peringatan
        source, _ = st.sprompt.text(scene, ws)
        if start:   # frame awal tidak bisa digabung dengan input_references (plan 18 Revisi 9): tanpa gambar/suara/previs, nama biasa di prompt
            built["refs"] = [{"kind": "frame", "n": 1, "label": f"frame akhir video adegan {start['scene_number']}", "clip_id": start["clip_id"]}]
            built["warnings"] = ["mode frame awal: gambar karakter, gambar latar, dan sampel suara tidak dikirim; wajah dan tempat mengikuti frame awal"]
            final = seedance_request.resolve(source, characters={}, location=0, known_locations=set())
        else:
            final = seedance_request.resolve(source, characters=built["map"]["characters"], location=built["map"]["location"], known_locations=set())
        extra = ([f"Visual style: {project['style'].strip().rstrip('.')}."] if project["style"].strip() else []) + \
                (["Start exactly from the provided first frame and continue seamlessly from it."] if start else [])
        if extra:   # gaya visual proyek (semua episode) dan instruksi frame awal: sebelum daftar SHOT
            lines = final.strip().split("\n")
            at = next((i for i, l in enumerate(lines) if l.lstrip().upper().startswith("SHOT ")), len(lines))
            final = "\n".join([*lines[:at], *extra, *lines[at:]])
        built["prompt"] = "\n".join(x for x in (final.strip(), built["references"], "", built["tail"]) if x is not None)
        if len(built["prompt"]) > PROMPT_MAX:
            raise ServiceError(f"prompt hasil rakitan {len(built['prompt'])} karakter (maks {PROMPT_MAX}); ringkas prompt adegan", 422)
        return {"scene": scene, "film": film, "info": info, "model": model, "duration": duration, "resolution": resolution,
                "aspect_ratio": ratio, "generate_audio": audio, "refs": built["refs"], "prompt": built["prompt"],
                "warnings": [*warnings, *built["warnings"]], "previs": previs, "total_seconds": total, "scene_prompt": source, "start": start}

    def estimate(self, plan: dict) -> pricing.Estimate:
        if plan["start"]:   # frame awal = gambar-ke-video 1 gambar, tanpa tarif video-input
            return pricing.estimate_video(plan["info"], duration=plan["duration"], resolution=plan["resolution"], audio=plan["generate_audio"],
                                          aspect_ratio=plan["aspect_ratio"], mode="i2v", image_inputs=1)
        return pricing.estimate_video(plan["info"], duration=plan["duration"], resolution=plan["resolution"], audio=plan["generate_audio"],
                                      aspect_ratio=plan["aspect_ratio"], mode="ref", reference_images=sum(1 for r in plan["refs"] if r["kind"] == "image"),
                                      video_input_seconds=plan["previs"]["duration"] if plan["previs"] else 0.0)

    def preview(self, scene_id: str, ws: str = DEFAULT_WS, use_previs: bool = False) -> dict:
        """Pratinjau tanpa efek samping: apa persis yang akan dikirim. Sampel suara hanya dihitung bila hosting publik aktif."""
        public_ok = not isinstance(self.st.public, NoPublicMedia)
        plan = self.plan(scene_id, ws, use_audio=public_ok, use_previs=use_previs, strict=False)
        voices_with_sample = [r for r in plan["refs"] if r["kind"] == "audio"]
        return {"model": plan["model"], "duration": plan["duration"], "resolution": plan["resolution"], "aspect_ratio": plan["aspect_ratio"],
                "generate_audio": plan["generate_audio"], "prompt": plan["prompt"], "scene_prompt": plan["scene_prompt"], "warnings": plan["warnings"],
                "refs": [{k: v for k, v in r.items()} for r in plan["refs"]], "public_media": public_ok,
                "previs_available": bool(plan["scene"]["previs_ref_id"]), "audio_refs": len(voices_with_sample),
                "start_from_scene_id": plan["scene"]["start_from_scene_id"], "start_candidates": self.start_candidates(plan["scene"], ws), "start_frame": ({"scene_number": plan["start"]["scene_number"], "clip_id": plan["start"]["clip_id"]} if plan["start"] else None),
                "start_info": {k: v for k, v in self.start_info(plan["scene"], ws).items() if k in ("ok", "reason", "scene_number", "clip_id")}}

    # ---------- kirim ----------
    def generate(self, scene_id: str, ws: str = DEFAULT_WS, *, prompt: str | None = None, use_previs: bool = False,
                 confirmed_cost: float | None = None, accept_unknown_cost: bool = False, idempotency_key: str | None = None) -> dict:
        st = self.st
        if idempotency_key:
            existing = st.db.one("SELECT scene_id FROM clips WHERE idempotency_key = ?", (idempotency_key,))
            if existing:
                return st.scenes.get(existing["scene_id"] or scene_id, ws)
        public_ok = not isinstance(st.public, NoPublicMedia)
        plan = self.plan(scene_id, ws, use_audio=public_ok, use_previs=use_previs)
        st.scenes._editable(plan["film"]["id"])
        final_prompt = (prompt if prompt is not None else plan["prompt"]).strip()
        if not final_prompt or len(final_prompt) > PROMPT_MAX:
            raise ServiceError(f"prompt kosong atau lebih dari {PROMPT_MAX} karakter", 422)

        keys: list[str] = []
        frame = None
        try:
            if plan["start"]:
                frame, frame_ref = self._start_frame(plan["start"], ws)   # ffmpeg di luar kunci Studio dan di luar transaksi
                payload_refs = []
            else:
                payload_refs = self._payload_refs(plan, ws, keys)
            with st._lock:
                est = self.estimate(plan)
                st.authorize(est, confirmed_cost, accept_unknown_cost, limits=False)
                payload = {"model": plan["model"], "prompt": final_prompt, "input_references": payload_refs, "duration": plan["duration"],
                           "resolution": plan["resolution"], "aspect_ratio": plan["aspect_ratio"], "generate_audio": plan["generate_audio"]}
                if plan["info"].get("generate_audio") is False:   # model tanpa parameter suara (HeyGen): jangan kirim
                    payload.pop("generate_audio")
                if frame:   # frame_images dan input_references tidak boleh digabung
                    payload.pop("input_references")
                    payload["frame_images"] = [frame_ref]
                dropped_audio = False
                try:
                    resp = self._submit(payload)
                except ServiceError as exc:
                    audio_refs = [r for r in payload_refs if r["type"] == "audio_url"]
                    if not audio_refs or exc.status not in (400, 422, 502):
                        raise
                    # penyedia menolak referensi audio: ulangi tanpa audio (suara dijelaskan lewat teks) daripada gagal total
                    retry = self.plan(scene_id, ws, use_audio=False, use_previs=use_previs)
                    payload = {**payload, "input_references": [r for r in payload_refs if r["type"] != "audio_url"],
                               "prompt": final_prompt if prompt is not None else retry["prompt"]}
                    resp = self._submit(payload)
                    dropped_audio = True
                params = {"mode": "storyboard", "duration": plan["duration"], "resolution": plan["resolution"], "aspect_ratio": plan["aspect_ratio"],
                          "generate_audio": plan["generate_audio"], "refs": [r["label"] for r in plan["refs"]]}
                if keys:
                    params["published_keys"] = keys
                if dropped_audio:
                    params["audio_ref_dropped"] = True
                first_image = frame["id"] if frame else next((r["image_id"] for r in plan["refs"] if r["kind"] == "image"), None)
                if frame:
                    params["start_from"] = {"scene_number": plan["start"]["scene_number"], "clip_id": plan["start"]["clip_id"], "image_id": frame["id"]}
                row = {"id": uuid.uuid4().hex, "parent_clip_id": None, "source_image_id": first_image, "prompt": payload["prompt"],
                       "model": plan["model"], "params": json.dumps(params), "status": "submitted", "remote_job_id": resp["id"],
                       "path": None, "merged_path": None, "cost": None, "estimated_cost": est.high, "error": None, "chain_depth": 0,
                       "idempotency_key": idempotency_key, "kind": "storyboard", "reference_id": plan["previs"]["id"] if plan["previs"] else None,
                       "created_at": now(), "updated_at": now(), "workspace_id": ws, "scene_id": scene_id}
                st.db.insert("clips", row)
                frame = None   # kepemilikan frame berpindah ke klip (source_image_id)
                keys = []   # kepemilikan berpindah ke klip: dilepas oleh _release_published saat job selesai
                cur = st.db.one("SELECT status FROM clips WHERE id = ? AND deleted_at IS NULL", (plan["scene"]["clip_id"],)) if plan["scene"]["clip_id"] else None
                if cur is None or cur["status"] in ("failed", "failed_download"):
                    st.db.update("scenes", scene_id, {"clip_id": row["id"], "updated_at": now()})
        except Exception:
            if frame:   # penolakan (biaya, penyedia) tidak boleh meninggalkan frame yatim di library
                st.db.execute("DELETE FROM images WHERE id = ?", (frame["id"],))
                st.storage.resolve(frame["path"]).unlink(missing_ok=True)
            raise
        finally:
            for k in keys:
                st.public.delete(k)
        return st.scenes.get(scene_id, ws)

    def _start_frame(self, start: dict, ws: str) -> tuple[dict, dict]:
        """Frame akhir video adegan sumber → gambar library (kind=frame) + elemen `frame_images` first_frame."""
        st = self.st
        tmp = st.storage.new_path(".png")
        try:
            media.extract_last_frame(st.storage.resolve(start["path"]), tmp)
            png, w, h = media.normalize_image(tmp.read_bytes())
        except media.MediaError as exc:
            raise ServiceError(f"gagal mengambil frame akhir video adegan {start['scene_number']}: {exc}", 422) from exc
        finally:
            tmp.unlink(missing_ok=True)
        frame = st._save_image(png, w, h, kind="frame", ws=ws)
        return frame, {"type": "image_url", "frame_type": "first_frame", "image_url": {"url": media.shrink_data_url(png)}}

    def _payload_refs(self, plan: dict, ws: str, keys: list[str]) -> list[dict]:
        st, out = self.st, []
        for r in plan["refs"]:
            if r["kind"] == "image":
                data = st.storage.resolve(st.get_image(r["image_id"], ws)["path"]).read_bytes()
                out.append({"type": "image_url", "image_url": {"url": media.shrink_data_url(data)}})
            elif r["kind"] == "audio":
                v = st.db.one("SELECT path FROM voice_versions WHERE id = ?", (r["voice_id"],))
                try:
                    key, url = st.public.publish(Path(v["path"]), "audio/mp4")
                except PublicMediaError as exc:
                    raise ServiceError(str(exc), 501) from exc
                keys.append(key)
                out.append({"type": "audio_url", "audio_url": {"url": url}})
            else:   # video previs
                try:
                    url, key = st.motion._public_url(plan["previs"])
                except PublicMediaError as exc:
                    raise ServiceError(str(exc), 501) from exc
                if key:
                    keys.append(key)
                out.append({"type": "video_url", "video_url": {"url": url}})
        return out

    def _submit(self, payload: dict) -> dict:
        try:
            resp = self.st.client.submit_video(payload)
        except OpenRouterError as exc:
            text = str(exc)
            if "SensitiveContent" in text or "real person" in text:
                raise ServiceError(f"{MODERATION_HINT} (pesan provider: {text[:200]})", 422) from exc
            raise ServiceError(text, 502 if exc.status is None or exc.status >= 500 else exc.status) from exc
        if not resp.get("id"):
            raise ServiceError("respons OpenRouter tidak berisi id job", 502)
        return resp
