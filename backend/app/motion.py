"""Tiru gerakan (plan 03). Tiga jalur hasil spike (docs/implementation/03-motion-transfer-spike.md):

  flux_edit    ganti subjek di video, prompt saja (cepat/murah; identitas perkiraan; audio asli terbawa)
  anchor_edit  kunci karakter: frame anchor (frame pertama + character sheet) + keyframe Aleph
  reference    animasikan gambar karakter dengan gerakan video (Seedance; ditolak untuk orang foto-realistik)
"""
import json
import time
import uuid
from pathlib import Path

from . import media, pricing
from .db import now
from .openrouter import OpenRouterError
from .service import DEFAULT_WS   # aman: service mengimpor motion secara lazy di Studio.__init__
from .publicmedia import NoPublicMedia, PublicMediaError

SEEDANCE = ["bytedance/seedance-2.0-mini", "bytedance/seedance-2.0-fast", "bytedance/seedance-2.0",
            "bytedance/seedance-2.5"]
MODE_MODELS = {
    "flux_edit": ["black-forest-labs/flux-video-edit"],
    "anchor_edit": ["runway/aleph-2"],
    "reference": SEEDANCE,
}
MIN_TRIM = 1.0   # detik
MODERATION_HINT = ("model menolak video referensi karena terdeteksi orang nyata/foto-realistik; jalur "
                   "'reference' (Seedance) hanya untuk subjek non-foto-realistik, gunakan 'anchor_edit' atau 'flux_edit'")


def _service_error(message: str, status: int = 400):
    from .service import ServiceError
    return ServiceError(message, status)


class Motion:
    def __init__(self, studio):
        self.st = studio

    # ---------- referensi ----------
    def add_upload(self, data_path: Path, ws: str = DEFAULT_WS) -> dict:
        """data_path: berkas sementara hasil unggahan; dinormalisasi dan disimpan sebagai referensi."""
        st = self.st
        out = st.storage.new_path(".mp4")
        try:
            probe = media.probe(data_path)
            if probe["duration"] > st.s.max_source_seconds + 0.25:
                raise _service_error(f"video {probe['duration']:.0f} dtk melebihi batas unggah "
                                     f"{st.s.max_source_seconds:.0f} dtk", 413)
            # plan 11: simpan utuh sampai batas unggah; user memotong rentangnya lewat trim
            info = media.prepare_reference_video(data_path, out, st.s.max_source_seconds)
        except media.MediaError as exc:
            out.unlink(missing_ok=True)
            raise _service_error(f"video tidak valid: {exc}", 415) from exc
        return self._save_ref(out, info, None, source_duration=probe["duration"], ws=ws)

    def add_from_clip(self, clip_id: str, ws: str = DEFAULT_WS) -> dict:
        clip = self.st.get_clip(clip_id, ws)
        if clip["status"] != "completed" or not clip["path"]:
            raise _service_error("klip belum selesai", 409)
        path = self.st.storage.resolve(clip["path"])
        info = media.probe(path)
        return self._save_ref(path, info, clip_id, ws=ws)

    def _save_ref(self, path: Path, info: dict, source_clip_id: str | None, source_duration: float | None = None,
                  ws: str = DEFAULT_WS) -> dict:
        row = {"id": uuid.uuid4().hex, "path": str(path), "source_clip_id": source_clip_id,
               "duration": info["duration"], "width": info["width"], "height": info["height"],
               "has_audio": 1 if info["has_audio"] else 0, "created_at": now(), "workspace_id": ws}
        self.st.db.insert("refs", row)
        return {**row, "has_audio": bool(row["has_audio"]),
                "trimmed": bool(source_duration and source_duration > info["duration"] + 0.2)}

    def trim(self, ref_id: str, start: float, end: float, ws: str = DEFAULT_WS) -> dict:
        """Referensi baru dari rentang [start, end] detik; referensi asal tidak berubah (plan 11)."""
        st = self.st
        ref = self.get_ref(ref_id, ws)
        end = min(end, ref["duration"])
        length = end - start
        if start < 0 or length < MIN_TRIM:
            raise _service_error(f"rentang tidak valid: minimal {MIN_TRIM:.0f} detik dan mulai dari 0 atau lebih")
        if length > st.s.max_reference_seconds + 0.01:
            raise _service_error(f"rentang {length:.1f} dtk melebihi batas {st.s.max_reference_seconds:.0f} dtk")
        if ref["source_clip_id"] and isinstance(st.public, NoPublicMedia):
            raise _service_error("hasil potong adalah berkas baru dan butuh URL publik (PUBLIC_TUNNEL=cloudflared "
                                 "atau S3/R2 di .env); tanpa itu hanya klip library utuh yang bisa dipakai", 501)
        src = Path(ref["path"])
        if not src.is_file():
            raise _service_error("berkas video referensi hilang dari disk", 410)
        out = st.storage.new_path(".mp4")
        try:
            info = media.prepare_reference_video(src, out, length, start=start)
        except media.MediaError as exc:
            out.unlink(missing_ok=True)
            raise _service_error(f"gagal memotong video: {exc}", 422) from exc
        return {**self._save_ref(out, info, None, ws=ws), "trimmed": True}

    def get_ref(self, ref_id: str, ws: str | None = DEFAULT_WS) -> dict:
        sql, args = "SELECT * FROM refs WHERE id = ?", [ref_id]
        if ws is not None:   # None hanya untuk berkas referensi (tanpa batas workspace)
            sql, args = sql + " AND workspace_id = ?", [*args, ws]
        row = self.st.db.one(sql, tuple(args))
        if not row:
            raise _service_error("referensi tidak ditemukan", 404)
        return row

    def _check_ref(self, ref: dict, mode: str) -> None:
        if ref["duration"] > self.st.s.max_reference_seconds + 0.25:
            raise _service_error(f"video referensi {ref['duration']:.1f} dtk melebihi batas "
                                 f"{self.st.s.max_reference_seconds:.0f} dtk (biaya mengikuti panjang video); "
                                 "potong dulu dengan panel Potong video")
        if mode == "reference" and ref["width"] * ref["height"] < media.MIN_REFERENCE_PIXELS and ref["source_clip_id"]:
            raise _service_error(f"klip referensi {ref['width']}x{ref['height']} terlalu kecil untuk Seedance "
                                 f"(minimal {media.MIN_REFERENCE_PIXELS:,} piksel, mis. 854x480); buat klip "
                                 "dengan resolusi lebih tinggi atau unggah videonya")

    def _public_url(self, ref: dict) -> tuple[str, str | None]:
        """(url, kunci_publikasi). Klip library memakai URL bertanda tangan OpenRouter; unggahan butuh storage publik."""
        st = self.st
        if ref["source_clip_id"]:
            clip = st.get_clip(ref["source_clip_id"], None)   # klip sumber milik workspace yang sama dengan referensi
            for _ in range(5):   # `urls` bisa muncul beberapa detik setelah job selesai
                try:
                    urls = st.client.get_video_job(clip["remote_job_id"]).get("urls")
                except OpenRouterError as exc:
                    raise _service_error(str(exc), 502) from exc
                if urls:
                    return urls[0], None
                time.sleep(2)
            raise _service_error("URL publik klip tidak tersedia (kedaluwarsa setelah sekitar 24 jam); "
                                 "unggah videonya agar disajikan lewat storage publik")
        try:
            key, url = st.public.publish(Path(ref["path"]))
        except PublicMediaError as exc:
            raise _service_error(str(exc), 501) from exc
        return url, key

    # ---------- validasi + estimasi ----------
    def _model_info(self, mode: str, model: str) -> dict:
        if mode not in MODE_MODELS:
            raise _service_error(f"mode tidak dikenal: {mode}")
        if model not in MODE_MODELS[mode]:
            raise _service_error(f"model {model} tidak diizinkan untuk mode {mode}; pilihan: {MODE_MODELS[mode]}")
        info = next((m for m in self.st.video_models() if m.get("id") == model), None)
        if info is None:
            raise _service_error(f"model tidak tersedia di OpenRouter saat ini: {model}")
        return info

    def _ref_images(self, character_id: str | None, image_ids: list[str]) -> list[str]:
        ids = list(image_ids)
        if character_id:
            sheet = [c["image_id"] for c in self.st.character_images(character_id)]
            ids = list(dict.fromkeys([*ids, *sheet]))
        return ids[:3]

    def estimate(self, mode: str, model: str, ref_id: str, *, duration: int | None = None,
                 resolution: str | None = None, aspect_ratio: str | None = None, generate_audio: bool = False,
                 n_images: int = 0, ws: str = DEFAULT_WS) -> pricing.Estimate:
        info = self._model_info(mode, model)
        ref = self.get_ref(ref_id, ws)
        self._check_ref(ref, mode)
        if mode == "reference":
            self._validate_reference_params(info, duration, resolution, aspect_ratio, generate_audio)
            return pricing.estimate_video(info, duration=duration, resolution=resolution, audio=generate_audio,
                                          aspect_ratio=aspect_ratio, mode="ref", reference_images=0,
                                          video_input_seconds=ref["duration"])
        return pricing.estimate_video(info, duration=None, resolution=None, audio=False, mode="edit",
                                      video_input_seconds=ref["duration"])

    def _validate_reference_params(self, info, duration, resolution, aspect_ratio, generate_audio) -> None:
        for key, value, field in (("duration", duration, "supported_durations"),
                                  ("resolution", resolution, "supported_resolutions"),
                                  ("aspect_ratio", aspect_ratio, "supported_aspect_ratios")):
            allowed = info.get(field)
            if value is not None and allowed and value not in allowed:
                raise _service_error(f"{key}={value} tidak didukung {info['id']}; pilihan: {allowed}")
        if generate_audio and info.get("generate_audio") is False:
            raise _service_error(f"{info['id']} tidak mendukung suara")

    # ---------- anchor frame (jalur anchor_edit) ----------
    def anchor_sheet(self, character_id: str, ws: str = DEFAULT_WS) -> list[str]:
        """Gambar referensi anchor; satu sumber untuk estimasi dan make_anchor (grill 09 bug 3)."""
        char = self.st.get_character(character_id, ws)
        return [c["image_id"] for c in self.st.character_images(character_id)
                if c["label"] in ("front", "side", "three_quarter")][:2] or [char["source_image_id"]]

    def make_anchor(self, ref_id: str, character_id: str, model: str, *, quality: str | None = None,
                    aspect_ratio: str | None = None, confirmed_cost=None, accept_unknown_cost=False,
                    ws: str = DEFAULT_WS) -> dict:
        st = self.st
        ref = self.get_ref(ref_id, ws)
        char = st.get_character(character_id, ws)
        sheet = self.anchor_sheet(character_id, ws)
        frame = st.storage.new_path(".png")
        try:
            media.first_frame(Path(ref["path"]), frame)
            png, w, h = media.normalize_image(frame.read_bytes())
        except media.MediaError as exc:
            raise _service_error(f"gagal mengambil frame pertama: {exc}", 422) from exc
        finally:
            frame.unlink(missing_ok=True)
        base = st._save_image(png, w, h, kind="frame", ws=ws)
        prompt = ("Edit image 1: replace the person with the character shown in the other reference images "
                  f"({char['description']}). Keep the exact pose, body position, framing, camera, background and "
                  "lighting of image 1 unchanged. Keep the face, hairstyle and clothing identical to the references.")
        try:
            out = st.edit_image(base["id"], prompt, model, sheet, quality=quality, aspect_ratio=aspect_ratio,
                                confirmed_cost=confirmed_cost, accept_unknown_cost=accept_unknown_cost, ws=ws)
        except Exception:
            st.db.execute("DELETE FROM images WHERE id = ?", (base["id"],))
            st.storage.resolve(base["path"]).unlink(missing_ok=True)
            raise
        st.db.execute("UPDATE images SET kind = 'anchor' WHERE id = ?", (out[0]["id"],))
        return {**out[0], "kind": "anchor"}

    # ---------- kirim job ----------
    def create(self, *, mode: str, model: str, ref_id: str, prompt: str, character_id: str | None = None,
               image_ids: list[str] | None = None, anchor_image_id: str | None = None,
               duration: int | None = None, resolution: str | None = None, aspect_ratio: str | None = None,
               generate_audio: bool = False, idempotency_key: str | None = None, subject_text: str | None = None,
               confirmed_cost: float | None = None, accept_unknown_cost: bool = False, ws: str = DEFAULT_WS,
               scene_id: str | None = None) -> dict:
        st = self.st
        if idempotency_key:
            existing = st.db.one("SELECT * FROM clips WHERE idempotency_key = ?", (idempotency_key,))
            if existing:
                return existing
        if not prompt.strip() or len(prompt) > 4000:
            raise _service_error("prompt kosong atau terlalu panjang")
        info = self._model_info(mode, model)
        ref = self.get_ref(ref_id, ws)
        self._check_ref(ref, mode)
        char = st.get_character(character_id, ws) if character_id else None
        params: dict = {"mode": mode}
        body_extra: dict = {}
        images: list[str] = []
        if mode == "flux_edit":
            # FLUX hanya membaca teks: subjek baru dikirim sebagai kata-kata. `subject_text` (diedit user) menggantikan
            # deskripsi baku karakter, yang bisa saja merujuk ke foto ("seperti di foto") dan ditolak penyedia.
            desc = (subject_text or (char["description"] if char else "")).strip()
            if desc:
                prompt = f"{prompt}\nThe new subject: {desc}"
        elif mode == "anchor_edit":
            if not anchor_image_id:
                raise _service_error("mode anchor_edit membutuhkan anchor_image_id (buat anchor dulu)")
            anchor = st.get_image(anchor_image_id, ws)
            if anchor["kind"] != "anchor":
                raise _service_error("gambar bukan anchor frame")
            anchor_url = media.to_data_url(st.storage.resolve(anchor["path"]).read_bytes())
            body_extra["provider"] = {"options": {"runway": {"keyframes": [{"uri": anchor_url, "seconds": 0}]}}}
        else:   # reference
            images = self._ref_images(character_id, image_ids or [])
            if not images:
                raise _service_error("mode reference membutuhkan karakter atau gambar subjek")
            self._validate_reference_params(info, duration, resolution, aspect_ratio, generate_audio)
            for k, v in {"duration": duration, "resolution": resolution, "aspect_ratio": aspect_ratio}.items():
                if v is not None:
                    params[k] = v
            params["generate_audio"] = generate_audio
        url, key = self._public_url(ref)   # di luar lock: bisa menunggu sampai 10 dtk (grill 09 bug 2)
        with st._lock:
            try:
                est = self.estimate(mode, model, ref_id, duration=duration, resolution=resolution,
                                    aspect_ratio=aspect_ratio, generate_audio=generate_audio, ws=ws)
                st.authorize(est, confirmed_cost, accept_unknown_cost)
            except Exception:
                if key:
                    st.public.delete(key)
                raise
            refs = [{"type": "video_url", "video_url": {"url": url}}]
            for iid in images:
                refs.append({"type": "image_url", "image_url": {"url": media.to_data_url(
                    st.storage.resolve(st.get_image(iid, ws)["path"]).read_bytes())}})
            payload = {"model": model, "prompt": prompt, "input_references": refs, **body_extra,
                       **{k: v for k, v in params.items() if k != "mode"}}
            try:
                resp = st.client.submit_video(payload)
            except OpenRouterError as exc:
                if key:
                    st.public.delete(key)
                text = str(exc)
                if "SensitiveContent" in text or "real person" in text:
                    raise _service_error(f"{MODERATION_HINT} (pesan provider: {text[:200]})", 422) from exc
                raise _service_error(text, 502) from exc
            if not resp.get("id"):
                if key:
                    st.public.delete(key)
                raise _service_error("respons OpenRouter tidak berisi id job", 502)
            if key:
                params["published_key"] = key
            row = {"id": uuid.uuid4().hex, "parent_clip_id": None, "source_image_id": anchor_image_id or (images[0] if images else None),
                   "prompt": prompt, "model": model, "params": json.dumps(params), "status": "submitted",
                   "remote_job_id": resp["id"], "path": None, "merged_path": None, "cost": None,
                   "estimated_cost": est.high, "error": None, "chain_depth": 0, "idempotency_key": idempotency_key,
                   "kind": "motion", "reference_id": ref_id, "created_at": now(), "updated_at": now(), "workspace_id": ws,
                   "scene_id": scene_id}
            st.db.insert("clips", row)
            return row
