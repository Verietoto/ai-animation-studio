import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import media
from .config import Settings
from .db import Database, now
from .openrouter import OpenRouterClient, OpenRouterError
from .storage import Storage

ACTIVE = ("submitted", "in_progress")
DONE_STATES = {"completed", "succeeded", "success"}
FAIL_STATES = {"failed", "error", "cancelled", "canceled", "expired"}


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Studio:
    def __init__(self, settings: Settings, db: Database, storage: Storage, client: OpenRouterClient):
        self.s, self.db, self.storage, self.client = settings, db, storage, client
        self._models: tuple[float, list[dict]] | None = None
        self._img_models: tuple[float, list[dict]] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------- guard ----------
    def _check_budget(self) -> None:
        if self.db.spent_today() >= self.s.daily_budget_usd:
            raise ServiceError(f"batas biaya harian ${self.s.daily_budget_usd:.2f} tercapai", 402)

    def video_models(self) -> list[dict]:
        if self._models and time.time() - self._models[0] < 300:
            return self._models[1]
        try:
            models = self.client.list_video_models()
        except OpenRouterError as exc:
            raise ServiceError(str(exc), 502) from exc
        self._models = (time.time(), models)
        return models

    def image_models(self) -> list[dict]:
        if self._img_models and time.time() - self._img_models[0] < 300:
            return self._img_models[1]
        try:
            models = self.client.list_image_models()
        except OpenRouterError as exc:
            raise ServiceError(str(exc), 502) from exc
        self._img_models = (time.time(), models)
        return models

    def _validate_image_params(self, model: str, options: dict, n_refs: int) -> None:
        info = next((m for m in self.image_models() if m.get("id") == model), None)
        if info is None:
            raise ServiceError(f"model gambar tidak dikenal atau tidak menerima input gambar: {model}")
        supported = info.get("supported_parameters") or {}
        for key, value in options.items():
            desc = supported.get(key)
            if desc is None:
                raise ServiceError(f"{model} tidak mendukung parameter {key}")
            if desc.get("type") == "enum" and value not in desc.get("values", []):
                raise ServiceError(f"{key}={value} tidak didukung {model}; pilihan: {desc['values']}")
        limit = (supported.get("input_references") or {}).get("max")
        if limit is not None and n_refs > limit:
            raise ServiceError(f"{model} menerima maksimal {limit} gambar input (dikirim {n_refs})")

    def _validate_video_params(self, model: str, params: dict) -> None:
        info = next((m for m in self.video_models() if m.get("id") == model), None)
        if info is None:
            raise ServiceError(f"model tidak dikenal: {model}")
        checks = [("duration", "supported_durations"), ("resolution", "supported_resolutions"),
                  ("aspect_ratio", "supported_aspect_ratios")]
        for key, field in checks:
            allowed = info.get(field)
            if params.get(key) is not None and allowed and params[key] not in allowed:
                raise ServiceError(f"{key}={params[key]} tidak didukung {model}; pilihan: {allowed}")
        frames = info.get("supported_frame_images")
        if not frames or "first_frame" not in frames:
            raise ServiceError(f"{model} tidak mendukung gambar sebagai frame awal (bukan model image-to-video)")
        if params.get("generate_audio") and info.get("generate_audio") is False:
            raise ServiceError(f"{model} tidak mendukung suara (generate_audio)")

    # ---------- images ----------
    def add_upload(self, data: bytes) -> dict:
        if len(data) > self.s.max_upload_bytes:
            raise ServiceError("file terlalu besar", 413)
        try:
            png, w, h = media.normalize_image(data)
        except media.MediaError as exc:
            raise ServiceError(str(exc), 415) from exc
        return self._save_image(png, w, h, kind="upload")

    def _save_image(self, png: bytes, w: int, h: int, *, kind: str, parent: str | None = None,
                    prompt: str | None = None, model: str | None = None, cost: float | None = None) -> dict:
        path = self.storage.save(png, ".png")
        row = {"id": uuid.uuid4().hex, "parent_image_id": parent, "kind": kind, "prompt": prompt,
               "model": model, "path": str(path), "width": w, "height": h, "cost": cost, "created_at": now()}
        self.db.insert("images", row)
        return row

    def get_image(self, image_id: str) -> dict:
        row = self.db.one("SELECT * FROM images WHERE id = ?", (image_id,))
        if not row:
            raise ServiceError("gambar tidak ditemukan", 404)
        return row

    def edit_image(self, image_id: str, prompt: str, model: str, reference_ids: list[str],
                   resolution: str | None = None, aspect_ratio: str | None = None,
                   quality: str | None = None) -> list[dict]:
        if not prompt.strip() or len(prompt) > 4000:
            raise ServiceError("prompt kosong atau terlalu panjang")
        reference_ids = reference_ids[:4]
        options = {k: v for k, v in {"resolution": resolution, "aspect_ratio": aspect_ratio,
                                     "quality": quality}.items() if v}
        self._validate_image_params(model, options, 1 + len(reference_ids))
        self._check_budget()
        source = self.get_image(image_id)
        urls = [media.to_data_url(self.storage.resolve(source["path"]).read_bytes())]
        for rid in reference_ids:
            urls.append(media.to_data_url(self.storage.resolve(self.get_image(rid)["path"]).read_bytes()))
        try:
            resp = self.client.edit_image(model, prompt, urls, **options)
        except OpenRouterError as exc:
            raise ServiceError(str(exc), 502) from exc
        images = [d.get("b64_json") for d in resp.get("data") or [] if d.get("b64_json")]
        if not images:
            raise ServiceError("model tidak mengembalikan gambar", 422)
        cost = (resp.get("usage") or {}).get("cost")
        out = []
        for n, b64 in enumerate(images):
            try:
                png, w, h = media.normalize_image(media.from_b64(b64, self.s.max_upload_bytes))
            except media.MediaError as exc:
                raise ServiceError(f"hasil edit tidak valid: {exc}", 502) from exc
            out.append(self._save_image(png, w, h, kind="edit", parent=image_id, prompt=prompt,
                                        model=model, cost=cost if n == 0 else None))
        return out

    # ---------- clips ----------
    def create_clip(self, *, image_id: str, prompt: str, model: str, duration: int | None = None,
                    resolution: str | None = None, aspect_ratio: str | None = None,
                    generate_audio: bool = False, idempotency_key: str | None = None,
                    parent_clip_id: str | None = None, chain_depth: int = 0) -> dict:
        if idempotency_key:
            existing = self.db.one("SELECT * FROM clips WHERE idempotency_key = ?", (idempotency_key,))
            if existing:
                return existing
        if not prompt.strip() or len(prompt) > 4000:
            raise ServiceError("prompt kosong atau terlalu panjang")
        params = {k: v for k, v in {"duration": duration, "resolution": resolution,
                                    "aspect_ratio": aspect_ratio}.items() if v is not None}
        params["generate_audio"] = generate_audio
        self._validate_video_params(model, params)
        self._check_budget()
        image = self.get_image(image_id)
        data_url = media.to_data_url(self.storage.resolve(image["path"]).read_bytes())
        payload = {"model": model, "prompt": prompt, **params,
                   "frame_images": [{"type": "image_url", "image_url": {"url": data_url},
                                     "frame_type": "first_frame"}]}
        try:
            resp = self.client.submit_video(payload)
        except OpenRouterError as exc:
            raise ServiceError(str(exc), 502) from exc
        remote_id = resp.get("id")
        if not remote_id:
            raise ServiceError("respons OpenRouter tidak berisi id job", 502)
        row = {"id": uuid.uuid4().hex, "parent_clip_id": parent_clip_id, "source_image_id": image_id,
               "prompt": prompt, "model": model, "params": json.dumps(params), "status": "submitted",
               "remote_job_id": remote_id, "path": None, "merged_path": None, "cost": None,
               "error": None, "chain_depth": chain_depth, "idempotency_key": idempotency_key,
               "created_at": now(), "updated_at": now()}
        self.db.insert("clips", row)
        return row

    def get_clip(self, clip_id: str) -> dict:
        row = self.db.one("SELECT * FROM clips WHERE id = ?", (clip_id,))
        if not row:
            raise ServiceError("klip tidak ditemukan", 404)
        return row

    def extend_clip(self, clip_id: str, prompt: str, model: str, **kw) -> dict:
        parent = self.get_clip(clip_id)
        if parent["status"] != "completed" or not parent["path"]:
            raise ServiceError("klip induk belum selesai", 409)
        depth = parent["chain_depth"] + 1
        if depth > self.s.max_chain:
            raise ServiceError(f"rantai extend maksimum {self.s.max_chain}; kualitas menurun pada rantai panjang")
        frame_path = self.storage.new_path(".png")
        try:
            media.extract_last_frame(self.storage.resolve(parent["path"]), frame_path)
            png, w, h = media.normalize_image(frame_path.read_bytes())
        except media.MediaError as exc:
            raise ServiceError(f"gagal mengambil frame akhir: {exc}", 422) from exc
        finally:
            frame_path.unlink(missing_ok=True)
        frame = self._save_image(png, w, h, kind="frame")
        return self.create_clip(image_id=frame["id"], prompt=prompt, model=model,
                                parent_clip_id=clip_id, chain_depth=depth, **kw)

    def merge_chain(self, clip_id: str) -> dict:
        chain, cur = [], self.get_clip(clip_id)
        while cur:
            if cur["status"] != "completed" or not cur["path"]:
                raise ServiceError("ada klip dalam rantai yang belum selesai", 409)
            chain.append(cur)
            cur = self.get_clip(cur["parent_clip_id"]) if cur["parent_clip_id"] else None
        chain.reverse()
        out = self.storage.new_path(".mp4")
        try:
            media.merge_videos([self.storage.resolve(c["path"]) for c in chain], out)
        except media.MediaError as exc:
            out.unlink(missing_ok=True)
            raise ServiceError(f"gagal menggabungkan: {exc}", 500) from exc
        self.db.update("clips", clip_id, {"merged_path": str(out), "updated_at": now()})
        return self.get_clip(clip_id)

    # ---------- polling ----------
    def poll_once(self) -> None:
        for clip in self.db.all("SELECT * FROM clips WHERE status IN ('submitted','in_progress')"):
            try:
                self._poll_clip(clip)
            except OpenRouterError as exc:
                # error jaringan sementara: biarkan, coba lagi di siklus berikut
                self.db.update("clips", clip["id"], {"error": str(exc), "updated_at": now()})

    def _poll_clip(self, clip: dict) -> None:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(clip["created_at"])).total_seconds()
        job = self.client.get_video_job(clip["remote_job_id"])
        status = str(job.get("status", "")).lower()
        cost = (job.get("usage") or {}).get("cost")
        if status in DONE_STATES:
            self.db.update("clips", clip["id"], {"cost": cost, "updated_at": now()})
            self._download(clip["id"], clip["remote_job_id"])
        elif status in FAIL_STATES:
            self.db.update("clips", clip["id"], {"status": "failed", "cost": cost, "updated_at": now(),
                                                 "error": str(job.get("error") or "job gagal")[:500]})
        elif age > self.s.job_timeout:
            self.db.update("clips", clip["id"], {"status": "failed", "updated_at": now(),
                                                 "error": "timeout menunggu job"})
        else:
            self.db.update("clips", clip["id"], {"status": "in_progress", "error": None, "updated_at": now()})

    def _download(self, clip_id: str, remote_id: str) -> None:
        try:
            data = self.client.download_video(remote_id)
            path = self.storage.save(data, ".mp4")
            media.probe(path)  # validasi file benar-benar video
        except (OpenRouterError, media.MediaError) as exc:
            self.db.update("clips", clip_id, {"status": "failed_download", "error": str(exc)[:500],
                                              "updated_at": now()})
            return
        self.db.update("clips", clip_id, {"status": "completed", "path": str(path), "error": None,
                                          "updated_at": now()})

    def retry_download(self, clip_id: str) -> dict:
        clip = self.get_clip(clip_id)
        if clip["status"] != "failed_download":
            raise ServiceError("klip tidak dalam status failed_download", 409)
        self._download(clip_id, clip["remote_job_id"])
        return self.get_clip(clip_id)

    # ---------- worker ----------
    def start(self) -> None:
        # job yang masih aktif saat startup otomatis dilanjutkan oleh loop yang sama
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:  # worker tidak boleh mati
                pass
            self._stop.wait(self.s.poll_interval)
