import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import media, pricing
from .config import Settings
from .db import Database, now
from .openrouter import OpenRouterClient, OpenRouterError
from .storage import Storage

ACTIVE = ("submitted", "in_progress")
DONE_STATES = {"completed", "succeeded", "success"}
FAIL_STATES = {"failed", "error", "cancelled", "canceled", "expired"}


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 400, extra: dict | None = None):
        super().__init__(message)
        self.status = status
        self.extra = extra or {}


class Studio:
    def __init__(self, settings: Settings, db: Database, storage: Storage, client: OpenRouterClient):
        self.s, self.db, self.storage, self.client = settings, db, storage, client
        self._models: tuple[float, list[dict]] | None = None
        self._img_models: tuple[float, list[dict]] | None = None
        self._lock = threading.RLock()   # cek anggaran + pencatatan job harus atomik
        self._endpoint_cache: dict[str, tuple[float, list[dict]]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------- guard ----------
    # ---------- biaya (plan 04) ----------
    def budget_state(self) -> dict:
        committed = self.db.committed_today()
        return {"committed_today": round(committed, 6), "daily_budget": self.s.daily_budget_usd,
                "remaining": round(max(self.s.daily_budget_usd - committed, 0.0), 6),
                "max_per_job": self.s.max_cost_per_job}

    def estimate_video_job(self, model: str, params: dict, *, mode: str = "i2v", image_inputs: int = 1,
                           reference_images: int = 0, video_input_seconds: float = 0.0) -> pricing.Estimate:
        info = next((m for m in self.video_models() if m.get("id") == model), None)
        if info is None:
            raise ServiceError(f"model tidak dikenal: {model}")
        return pricing.estimate_video(
            info, duration=params.get("duration"), resolution=params.get("resolution"),
            audio=bool(params.get("generate_audio")), aspect_ratio=params.get("aspect_ratio"), mode=mode,
            image_inputs=image_inputs, reference_images=reference_images, video_input_seconds=video_input_seconds)

    def _image_endpoints(self, model: str) -> list[dict]:
        cached = self._endpoint_cache.get(model)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        try:
            endpoints = self.client.get_image_endpoints(model)
        except OpenRouterError as exc:
            raise ServiceError(str(exc), 502) from exc
        self._endpoint_cache[model] = (time.time(), endpoints)
        return endpoints

    def estimate_image_job(self, model: str, *, n_inputs: int, resolution: str | None = None,
                           n_outputs: int = 1) -> pricing.Estimate:
        rows = self.db.all("SELECT cost FROM images WHERE model = ? AND cost IS NOT NULL "
                           "ORDER BY created_at DESC LIMIT 20", (model,))
        return pricing.estimate_image(self._image_endpoints(model), n_outputs=n_outputs, n_inputs=n_inputs,
                                      resolution=resolution, history=[r["cost"] for r in rows] or None)

    def authorize(self, est: pricing.Estimate, confirmed_cost: float | None, accept_unknown: bool) -> None:
        """Server tidak mempercayai browser: hitung ulang, bandingkan dengan yang dikonfirmasi, cek batas."""
        info = {"estimate": est.as_dict(), **self.budget_state()}
        if est.confidence == "unknown":
            if not accept_unknown:
                raise ServiceError("biaya tidak diketahui; konfirmasi eksplisit diperlukan "
                                   "(accept_unknown_cost)", 409, info)
        else:
            if confirmed_cost is None:
                raise ServiceError("konfirmasi estimasi biaya diperlukan (confirmed_cost)", 409, info)
            if est.high > confirmed_cost + 1e-4:
                raise ServiceError(f"estimasi berubah menjadi ${est.high:.4f} (dikonfirmasi ${confirmed_cost:.4f}); "
                                   "konfirmasi ulang", 409, info)
            if est.high > self.s.max_cost_per_job:
                raise ServiceError(f"estimasi ${est.high:.4f} melebihi batas per job ${self.s.max_cost_per_job:.2f} "
                                   "(ubah MAX_COST_PER_JOB_USD bila disengaja)", 402, info)
        if self.db.committed_today() + est.high > self.s.daily_budget_usd:
            raise ServiceError(f"melebihi batas harian ${self.s.daily_budget_usd:.2f} "
                               f"(terpakai/terpesan ${self.db.committed_today():.4f} + estimasi ${est.high:.4f})",
                               402, info)

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
                    prompt: str | None = None, model: str | None = None, cost: float | None = None,
                    estimated: float | None = None) -> dict:
        path = self.storage.save(png, ".png")
        row = {"id": uuid.uuid4().hex, "parent_image_id": parent, "kind": kind, "prompt": prompt,
               "model": model, "path": str(path), "width": w, "height": h, "cost": cost,
               "estimated_cost": estimated, "created_at": now()}
        self.db.insert("images", row)
        return row

    def get_image(self, image_id: str) -> dict:
        row = self.db.one("SELECT * FROM images WHERE id = ?", (image_id,))
        if not row:
            raise ServiceError("gambar tidak ditemukan", 404)
        return row

    def edit_image(self, image_id: str, prompt: str, model: str, reference_ids: list[str],
                   resolution: str | None = None, aspect_ratio: str | None = None,
                   quality: str | None = None, confirmed_cost: float | None = None,
                   accept_unknown_cost: bool = False, character_id: str | None = None) -> list[dict]:
        if not prompt.strip() or len(prompt) > 4000:
            raise ServiceError("prompt kosong atau terlalu panjang")
        if character_id:   # kunci karakter: gambar sheet jadi referensi + deskripsi baku masuk ke prompt
            char = self.get_character(character_id)
            sheet = [c["image_id"] for c in self.character_images(character_id) if c["image_id"] != image_id]
            reference_ids = list(dict.fromkeys([*sheet, *reference_ids]))
            prompt = f"{prompt}\nKeep the character consistent with the reference images: {char['description']}"
        reference_ids = reference_ids[:4]
        options = {k: v for k, v in {"resolution": resolution, "aspect_ratio": aspect_ratio,
                                     "quality": quality}.items() if v}
        self._validate_image_params(model, options, 1 + len(reference_ids))
        with self._lock:
            est = self.estimate_image_job(model, n_inputs=1 + len(reference_ids), resolution=resolution)
            self.authorize(est, confirmed_cost, accept_unknown_cost)
            return self._run_edit(image_id, prompt, model, reference_ids, options, est)

    def _run_edit(self, image_id: str, prompt: str, model: str, reference_ids: list[str], options: dict,
                  est: pricing.Estimate, kind: str = "edit") -> list[dict]:
        source = self.get_image(image_id)
        urls = [media.to_data_url(self.storage.resolve(source["path"]).read_bytes())]
        for rid in reference_ids:
            urls.append(media.to_data_url(self.storage.resolve(self.get_image(rid)["path"]).read_bytes()))
        try:
            resp = self.client.edit_image(model, prompt, urls, **options)
        except OpenRouterError as exc:
            raise ServiceError(str(exc), 502) from exc
        return self._store_edit_results(resp, image_id, prompt, model, est, kind)

    def _store_edit_results(self, resp: dict, image_id: str, prompt: str, model: str, est: pricing.Estimate,
                            kind: str = "edit") -> list[dict]:
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
            out.append(self._save_image(png, w, h, kind=kind, parent=image_id, prompt=prompt, model=model,
                                        cost=cost if n == 0 else None, estimated=est.high if n == 0 else None))
        return out

    # ---------- clips ----------
    def create_clip(self, *, image_id: str, prompt: str, model: str, duration: int | None = None,
                    resolution: str | None = None, aspect_ratio: str | None = None,
                    generate_audio: bool = False, idempotency_key: str | None = None,
                    parent_clip_id: str | None = None, chain_depth: int = 0,
                    confirmed_cost: float | None = None, accept_unknown_cost: bool = False) -> dict:
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
        with self._lock:   # cek anggaran, kirim, dan catat estimasi tanpa celah balapan
            est = self.estimate_video_job(model, params)
            self.authorize(est, confirmed_cost, accept_unknown_cost)
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
                   "estimated_cost": est.high, "error": None, "chain_depth": chain_depth,
                   "idempotency_key": idempotency_key, "created_at": now(), "updated_at": now()}
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
        try:
            return self.create_clip(image_id=frame["id"], prompt=prompt, model=model,
                                    parent_clip_id=clip_id, chain_depth=depth, **kw)
        except ServiceError:   # penolakan (biaya, validasi) tidak boleh meninggalkan frame yatim
            self.db.execute("DELETE FROM images WHERE id = ?", (frame["id"],))
            self.storage.resolve(frame["path"]).unlink(missing_ok=True)
            raise

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


    # ---------- karakter (plan 03: kunci karakter) ----------
    SHEET_VIEWS = [
        ("front", "Character reference sheet: front view of the same character as in the reference image, "
                  "face fully visible, neutral expression, plain light-gray background."),
        ("side", "Character reference sheet: side profile view of the same character as in the reference image, "
                 "plain light-gray background."),
        ("three_quarter", "Character reference sheet: three-quarter view of the same character as in the reference "
                          "image, plain light-gray background."),
        ("full_body", "Character reference sheet: full body, head to toe, standing, front view of the same character "
                      "as in the reference image, plain light-gray background."),
    ]
    SHEET_SUFFIX = " Keep the face, hairstyle, clothing, accessories and colors exactly identical. No text, no labels."

    def create_character(self, name: str, description: str, source_image_id: str) -> dict:
        if not name.strip() or not description.strip():
            raise ServiceError("nama dan deskripsi karakter wajib diisi")
        if len(name) > 80 or len(description) > 2000:
            raise ServiceError("nama maks 80 dan deskripsi maks 2000 karakter")
        self.get_image(source_image_id)
        row = {"id": uuid.uuid4().hex, "name": name.strip(), "description": description.strip(),
               "source_image_id": source_image_id, "created_at": now()}
        self.db.insert("characters", row)
        self.db.insert("character_images", {"character_id": row["id"], "image_id": source_image_id, "label": "source"})
        return row

    def get_character(self, character_id: str) -> dict:
        row = self.db.one("SELECT * FROM characters WHERE id = ?", (character_id,))
        if not row:
            raise ServiceError("karakter tidak ditemukan", 404)
        return row

    def character_images(self, character_id: str) -> list[dict]:
        return self.db.all("SELECT image_id, label FROM character_images WHERE character_id = ? "
                           "ORDER BY rowid", (character_id,))

    def add_character_image(self, character_id: str, image_id: str, label: str = "custom") -> None:
        self.get_character(character_id)
        self.get_image(image_id)
        self.db.execute("INSERT OR REPLACE INTO character_images (character_id, image_id, label) VALUES (?, ?, ?)",
                        (character_id, image_id, label[:30]))

    def estimate_sheet(self, model: str, n_views: int, aspect_ratio: str | None = None,
                       quality: str | None = None) -> pricing.Estimate:
        options = {k: v for k, v in {"aspect_ratio": aspect_ratio, "quality": quality}.items() if v}
        self._validate_image_params(model, options, 1)
        one = self.estimate_image_job(model, n_inputs=1)
        return pricing.Estimate(one.low * n_views, one.high * n_views, one.confidence,
                                [f"{n_views} gambar x ({b})" for b in one.basis[:1]] + one.basis[1:])

    def generate_sheet(self, character_id: str, model: str, aspect_ratio: str | None = None,
                       quality: str | None = None, confirmed_cost: float | None = None,
                       accept_unknown_cost: bool = False) -> list[dict]:
        char = self.get_character(character_id)
        options = {k: v for k, v in {"aspect_ratio": aspect_ratio, "quality": quality}.items() if v}
        self._validate_image_params(model, options, 1)
        with self._lock:
            est = self.estimate_sheet(model, len(self.SHEET_VIEWS), aspect_ratio, quality)
            self.authorize(est, confirmed_cost, accept_unknown_cost)
            per_view = pricing.Estimate(est.low / len(self.SHEET_VIEWS), est.high / len(self.SHEET_VIEWS),
                                        est.confidence, est.basis)
            out = []
            for label, prompt in self.SHEET_VIEWS:
                full = f"{prompt}{self.SHEET_SUFFIX} Character details: {char['description']}"
                images = self._run_edit(char["source_image_id"], full, model, [], options, per_view, kind="sheet")
                for img in images:
                    self.add_character_image(character_id, img["id"], label)
                out.extend(images)
            return out
