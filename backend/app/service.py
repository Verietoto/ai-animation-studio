import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import editprompt, media, pricing, sceneprompt
from .config import Settings
from .db import Database, now
from .openrouter import OpenRouterClient, OpenRouterError
from .publicmedia import NoPublicMedia
from .storage import Storage

ACTIVE = ("submitted", "in_progress")
DEFAULT_WS = "main"   # workspace "Utama": data lama, dan klien/tes yang tidak mengirim X-Workspace-Id
DONE_STATES = {"completed", "succeeded", "success"}
FAIL_STATES = {"failed", "error", "cancelled", "canceled", "expired"}


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 400, extra: dict | None = None):
        super().__init__(message)
        self.status = status
        self.extra = extra or {}


class Studio:
    def __init__(self, settings: Settings, db: Database, storage: Storage, client: OpenRouterClient,
                 public=None):
        self.s, self.db, self.storage, self.client = settings, db, storage, client
        self.public = public or NoPublicMedia()
        from .motion import Motion
        self.motion = Motion(self)
        from .films import Films
        self.films = Films(self)
        from .scenes import Scenes
        self.scenes = Scenes(self)
        from .journey import Journey
        self.journey = Journey(self)
        from .workspaces import Workspaces
        self.workspaces = Workspaces(self)
        from .voices import Voices
        self.voices = Voices(self)
        from .beats import Beats
        self.beats = Beats(self)
        from .storyboard_video import StoryboardVideo
        self.sbvideo = StoryboardVideo(self)
        from .scene_prompt import ScenePrompt
        self.sprompt = ScenePrompt(self)
        self._models: tuple[float, list[dict]] | None = None
        self._img_models: tuple[float, list[dict]] | None = None
        self._all_img_models: tuple[float, list[dict]] | None = None   # termasuk model teks-saja (katalog)
        self._text_catalog: tuple[float, list[dict]] | None = None   # daftar model teks yang disaring (plan 17), cache 5 menit
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

    def _video_endpoints(self, model: str) -> list[dict]:
        key = f"video:{model}"
        cached = self._endpoint_cache.get(key)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        try:
            endpoints = self.client.get_video_endpoints(model)
        except OpenRouterError as exc:
            raise ServiceError(str(exc), 502) from exc
        self._endpoint_cache[key] = (time.time(), endpoints)
        return endpoints

    @staticmethod
    def _negative_param(info: dict) -> str | None:
        """Nama parameter negative prompt model ini (`negative_prompt` / `negativePrompt`), dari katalog."""
        return next((p for p in info.get("allowed_passthrough_parameters") or []
                     if p in ("negative_prompt", "negativePrompt")), None)

    def _provider_options(self, model: str, values: dict) -> dict:
        """provider.options per slug penyedia. Kunci yang salah diabaikan diam-diam oleh OpenRouter (grill 13),
        jadi slug diambil dari endpoint API, dan dikirim ke semua penyedia model ini (hanya yang melayani meneruskan)."""
        slugs = [e["tag"] for e in self._video_endpoints(model) if e.get("tag")]
        if not slugs:
            raise ServiceError(f"penyedia {model} tidak diketahui; negative prompt tidak bisa dikirim", 502)
        # google-vertex memakai lapisan "parameters" (contoh resmi docs video-generation); atlas-cloud datar (contoh Vercel AI SDK)
        return {"options": {s: {"parameters": dict(values)} if s == "google-vertex" else dict(values) for s in slugs}}

    def estimate_image_job(self, model: str, *, n_inputs: int, resolution: str | None = None,
                           n_outputs: int = 1) -> pricing.Estimate:
        rows = self.db.all("SELECT cost FROM images WHERE model = ? AND cost IS NOT NULL "
                           "ORDER BY created_at DESC LIMIT 20", (model,))
        return pricing.estimate_image(self._image_endpoints(model), n_outputs=n_outputs, n_inputs=n_inputs,
                                      resolution=resolution, history=[r["cost"] for r in rows] or None)

    def authorize(self, est: pricing.Estimate, confirmed_cost: float | None, accept_unknown: bool, limits: bool = True) -> None:
        """Server tidak mempercayai browser: hitung ulang, bandingkan dengan yang dikonfirmasi, cek batas.
        `limits=False` (Storyboard v2, plan 18 Revisi 2): konfirmasi tetap wajib, batas per job dan harian tidak memblokir."""
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
            if limits and est.high > self.s.max_cost_per_job:
                raise ServiceError(f"estimasi ${est.high:.4f} melebihi batas per job ${self.s.max_cost_per_job:.2f} "
                                   "(ubah MAX_COST_PER_JOB_USD bila disengaja)", 402, info)
        if limits and self.db.committed_today() + est.high > self.s.daily_budget_usd:
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

    # ---------- katalog model + harga (plan 05) ----------
    def video_catalog(self, refresh: bool = False) -> dict:
        if refresh:
            self._models = None
        models = self.video_models()
        cards = [{"id": m.get("id"), "name": m.get("name") or m.get("id"), "provider": (m.get("id") or "").split("/")[0],
                  "description": (m.get("description") or "")[:240],
                  "capabilities": {"first_frame": "first_frame" in (m.get("supported_frame_images") or []),
                                   "last_frame": "last_frame" in (m.get("supported_frame_images") or []),
                                   "audio": m.get("generate_audio"), "durations": m.get("supported_durations") or [],
                                   "resolutions": m.get("supported_resolutions") or [],
                                   "aspect_ratios": m.get("supported_aspect_ratios") or [],
                                   "negative_prompt": self._negative_param(m)},
                  "price": pricing.video_price_card(m)} for m in models]
        return {"fetched_at": datetime.now(timezone.utc).isoformat(), "models": cards}

    def image_catalog(self, refresh: bool = False) -> dict:
        from concurrent.futures import ThreadPoolExecutor
        if refresh:
            self._all_img_models = None
            self._endpoint_cache.clear()
        if not self._all_img_models or time.time() - self._all_img_models[0] >= 300:
            try:
                self._all_img_models = (time.time(), self.client.list_all_image_models())
            except OpenRouterError as exc:
                raise ServiceError(str(exc), 502) from exc
        models = self._all_img_models[1]

        def card(m: dict) -> dict:
            mid = m.get("id") or ""
            try:
                endpoints, err = self._image_endpoints(mid), None
            except ServiceError as exc:   # satu model gagal tidak boleh menjatuhkan katalog
                endpoints, err = None, str(exc)
            hist = [r["cost"] for r in self.db.all("SELECT cost FROM images WHERE model = ? AND cost IS NOT NULL "
                                                   "ORDER BY created_at DESC LIMIT 20", (mid,))] or None
            params = m.get("supported_parameters") or {}
            return {"id": mid, "name": m.get("name") or mid, "provider": mid.split("/")[0],
                    "description": (m.get("description") or "")[:240],
                    "capabilities": {"max_references": (params.get("input_references") or {}).get("max"),
                                     "aspect_ratios": (params.get("aspect_ratio") or {}).get("values") or [],
                                     "quality": (params.get("quality") or {}).get("values") or []},
                    "price": pricing.image_price_card(m, endpoints, err, hist)}
        with ThreadPoolExecutor(max_workers=6) as pool:
            cards = list(pool.map(card, models))
        return {"fetched_at": datetime.now(timezone.utc).isoformat(), "models": cards}

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
    def add_upload(self, data: bytes, ws: str = DEFAULT_WS) -> dict:
        if len(data) > self.s.max_upload_bytes:
            raise ServiceError("file terlalu besar", 413)
        try:
            png, w, h = media.normalize_image(data)
        except media.MediaError as exc:
            raise ServiceError(str(exc), 415) from exc
        return self._save_image(png, w, h, kind="upload", ws=ws)

    def _save_image(self, png: bytes, w: int, h: int, *, kind: str, ws: str = DEFAULT_WS, parent: str | None = None,
                    prompt: str | None = None, model: str | None = None, cost: float | None = None,
                    estimated: float | None = None, scene_id: str | None = None) -> dict:
        path = self.storage.save(png, ".png")
        row = {"id": uuid.uuid4().hex, "parent_image_id": parent, "kind": kind, "prompt": prompt,
               "model": model, "path": str(path), "width": w, "height": h, "cost": cost,
               "estimated_cost": estimated, "created_at": now(), "workspace_id": ws, "scene_id": scene_id}
        self.db.insert("images", row)
        return row

    def get_image(self, image_id: str, ws: str | None = DEFAULT_WS) -> dict:
        """ws = workspace yang dipakai; None hanya untuk akses internal/berkas (tanpa batas workspace).
        Default DEFAULT_WS (bukan None) supaya pemanggil yang lupa mengirim ws gagal 404, bukan membocorkan data."""
        sql, args = "SELECT * FROM images WHERE id = ? AND deleted_at IS NULL", [image_id]
        if ws is not None:
            sql, args = sql + " AND workspace_id = ?", [*args, ws]
        row = self.db.one(sql, tuple(args))
        if not row:
            raise ServiceError("gambar tidak ditemukan", 404)
        return row

    def edit_image(self, image_id: str, prompt: str, model: str, reference_ids: list[str],
                   resolution: str | None = None, aspect_ratio: str | None = None,
                   quality: str | None = None, confirmed_cost: float | None = None,
                   accept_unknown_cost: bool = False, character_id: str | None = None,
                   pose_image_id: str | None = None, pose_mode: str = "sketch", expression_image_id: str | None = None,
                   pose_text: str | None = None, expression_text: str | None = None, ws: str = DEFAULT_WS) -> list[dict]:
        if not prompt.strip() or len(prompt) > 4000:
            raise ServiceError("prompt kosong atau terlalu panjang")
        plan = self.plan_edit(image_id, model, character_id=character_id, pose_image_id=pose_image_id, pose_mode=pose_mode,
                              expression_image_id=expression_image_id, reference_ids=reference_ids,
                              pose_text=pose_text, expression_text=expression_text, ws=ws)
        prompt = editprompt.build_prompt(prompt, plan)
        if len(prompt) > 4000:   # dicek pada prompt akhir: instruksi peran menambah panjang
            raise ServiceError("prompt terlalu panjang setelah instruksi referensi ditambahkan (maks 4000 karakter); ringkas prompt")
        n_inputs = len(plan.entries)
        options = {k: v for k, v in {"resolution": resolution, "aspect_ratio": aspect_ratio,
                                     "quality": quality}.items() if v}
        self._validate_image_params(model, options, n_inputs)
        with self._lock:
            est = self.estimate_image_job(model, n_inputs=n_inputs, resolution=resolution)
            self.authorize(est, confirmed_cost, accept_unknown_cost)
            return self._run_edit(image_id, prompt, model, [], options, est, extra_urls=self._plan_urls(plan, ws), ws=ws)

    def plan_edit(self, image_id: str, model: str, *, character_id: str | None = None, pose_image_id: str | None = None,
                  pose_mode: str = "sketch", expression_image_id: str | None = None, reference_ids=(),
                  pose_text: str | None = None, expression_text: str | None = None, ws: str = DEFAULT_WS) -> editprompt.EditPlan:
        """Satu sumber kebenaran daftar gambar input; dipakai /api/estimate dan edit_image."""
        for iid in (image_id, pose_image_id, expression_image_id, *reference_ids):
            if iid:
                self.get_image(iid, ws)   # 404 bila tidak ada / sudah dihapus / milik workspace lain
        char = self.get_character(character_id, ws) if character_id else None
        sheet = [(c["image_id"], c["label"]) for c in self.character_images(character_id)] if character_id else []
        info = next((m for m in self.image_models() if m.get("id") == model), None)
        limit = ((info or {}).get("supported_parameters") or {}).get("input_references", {}).get("max")
        try:
            entries = editprompt.plan_inputs(image_id, sheet, pose_id=pose_image_id, pose_mode=pose_mode,
                                             expression_id=expression_image_id, reference_ids=list(reference_ids),
                                             max_inputs=limit if limit is not None else 5)   # 5 = 1 sumber + 4 referensi (perilaku lama)
            return editprompt.EditPlan(entries, char, editprompt.clean_text(pose_text, "pose"),
                                       editprompt.clean_text(expression_text, "ekspresi"))
        except editprompt.InputError as exc:
            raise ServiceError(str(exc), 400) from exc

    def _plan_urls(self, plan: editprompt.EditPlan, ws: str = DEFAULT_WS) -> list[str]:
        urls = []
        for e in plan.entries[1:]:
            data = self.storage.resolve(self.get_image(e.image_id, ws)["path"]).read_bytes()
            urls.append(media.to_data_url(editprompt.make_pose_sketch(data) if e.transform == "sketch" else data))
        return urls

    def _run_edit(self, image_id: str, prompt: str, model: str, reference_ids: list[str], options: dict,
                  est: pricing.Estimate, kind: str = "edit", extra_urls: list[str] | None = None,
                  ws: str = DEFAULT_WS, scene_id: str | None = None) -> list[dict]:
        source = self.get_image(image_id, ws)
        urls = [media.to_data_url(self.storage.resolve(source["path"]).read_bytes())]
        if extra_urls is not None:   # daftar akhir dari plan_edit (sudah berurutan dan bertransformasi)
            urls += extra_urls
        for rid in ([] if extra_urls is not None else reference_ids):
            urls.append(media.to_data_url(self.storage.resolve(self.get_image(rid, ws)["path"]).read_bytes()))
        try:
            resp = self.client.edit_image(model, prompt, urls, **options)
        except OpenRouterError as exc:
            raise ServiceError(str(exc), 502) from exc
        return self._store_edit_results(resp, image_id, prompt, model, est, kind, ws, scene_id)

    def _store_edit_results(self, resp: dict, image_id: str | None, prompt: str, model: str, est: pricing.Estimate,
                            kind: str = "edit", ws: str = DEFAULT_WS, scene_id: str | None = None) -> list[dict]:
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
            out.append(self._save_image(png, w, h, kind=kind, ws=ws, parent=image_id, prompt=prompt, model=model,
                                        cost=cost if n == 0 else None, estimated=est.high if n == 0 else None, scene_id=scene_id))
        return out

    # ---------- clips ----------
    def create_clip(self, *, image_id: str, prompt: str, model: str, duration: int | None = None,
                    resolution: str | None = None, aspect_ratio: str | None = None,
                    generate_audio: bool = False, idempotency_key: str | None = None,
                    parent_clip_id: str | None = None, chain_depth: int = 0,
                    confirmed_cost: float | None = None, accept_unknown_cost: bool = False, ws: str = DEFAULT_WS,
                    scene_id: str | None = None, last_image_id: str | None = None,
                    negative_prompt: str | None = None) -> dict:
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
        frames = [(image_id, "first_frame")]
        if last_image_id:   # plan 09: frame akhir opsional
            info = next(m for m in self.video_models() if m.get("id") == model)
            if "last_frame" not in (info.get("supported_frame_images") or []):
                raise ServiceError(f"{model} tidak mendukung frame akhir")
            frames.append((last_image_id, "last_frame"))
        negative_prompt = (negative_prompt or "").strip() or None
        provider = None
        if negative_prompt:   # plan 13: hanya model yang katalognya mengizinkan; dicek sebelum biaya keluar
            info = next((m for m in self.video_models() if m.get("id") == model), {})
            name = self._negative_param(info)
            if not name:
                raise ServiceError(f"{model} tidak mendukung negative prompt")
            provider = self._provider_options(model, {name: negative_prompt})
        with self._lock:   # cek anggaran, kirim, dan catat estimasi tanpa celah balapan
            est = self.estimate_video_job(model, params)
            self.authorize(est, confirmed_cost, accept_unknown_cost)
            frame_images = [{"type": "image_url", "frame_type": kind, "image_url": {"url": media.to_data_url(
                self.storage.resolve(self.get_image(iid, ws)["path"]).read_bytes())}} for iid, kind in frames]
            payload = {"model": model, "prompt": prompt, **params, "frame_images": frame_images}
            if provider:
                payload["provider"] = provider
                params["negative_prompt"] = negative_prompt   # jejak di params, seperti last_image_id
            if last_image_id:
                params["last_image_id"] = last_image_id   # disimpan di params, tidak dikirim sebagai field
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
                   "idempotency_key": idempotency_key, "created_at": now(), "updated_at": now(), "workspace_id": ws,
                   "scene_id": scene_id}
            self.db.insert("clips", row)
            return row

    def get_clip(self, clip_id: str, ws: str | None = DEFAULT_WS) -> dict:
        sql, args = "SELECT * FROM clips WHERE id = ? AND deleted_at IS NULL", [clip_id]
        if ws is not None:
            sql, args = sql + " AND workspace_id = ?", [*args, ws]
        row = self.db.one(sql, tuple(args))
        if not row:
            raise ServiceError("klip tidak ditemukan", 404)
        return row

    # ---------- hapus (soft delete; plan 05 revisi 3) ----------
    def _unlink(self, stored: str | None) -> None:
        if stored:
            try:
                self.storage.resolve(stored).unlink(missing_ok=True)
            except ValueError:
                pass   # path di luar storage: jangan disentuh

    def delete_image(self, image_id: str, ws: str = DEFAULT_WS) -> None:
        with self._lock:
            img = self.get_image(image_id, ws)
            owner = self.db.one("SELECT c.name FROM character_images ci JOIN characters c ON c.id = ci.character_id "
                                "WHERE ci.image_id = ? LIMIT 1", (image_id,))
            if owner:
                raise ServiceError(f"gambar dipakai karakter \"{owner['name']}\"; hapus karakternya dulu", 409)
            if self.db.one("SELECT 1 FROM clips WHERE source_image_id = ? AND deleted_at IS NULL "
                           "AND status IN ('submitted','in_progress')", (image_id,)):
                raise ServiceError("gambar dipakai job yang masih berjalan", 409)
            used = self.db.one("SELECT name FROM locations WHERE image_id = ? LIMIT 1", (image_id,))
            if used:
                raise ServiceError(f"gambar dipakai latar \"{used['name']}\"; hapus latarnya dulu", 409)
            used = self.db.one("SELECT name FROM outfits WHERE image_id = ? LIMIT 1", (image_id,))
            if used:
                raise ServiceError(f"gambar dipakai tampilan \"{used['name']}\"; hapus tampilannya dulu", 409)
            self._unlink(img["path"])
            # path NOT NULL di skema lama: string kosong menandai "file sudah dihapus"
            with self.db.transaction() as tx:
                tx.execute("UPDATE scenes SET keyframe_image_id = NULL, updated_at = ? WHERE keyframe_image_id = ?", (now(), image_id))
                tx.execute("UPDATE scenes SET blockout_image_id = NULL WHERE blockout_image_id = ?", (image_id,))
                tx.execute("UPDATE images SET deleted_at = ?, path = '' WHERE id = ?", (now(), image_id))

    def delete_clip(self, clip_id: str, ws: str = DEFAULT_WS) -> None:
        with self._lock:
            clip = self.get_clip(clip_id, ws)
            if clip["status"] in ACTIVE:
                raise ServiceError("klip masih diproses; tunggu selesai", 409)
            if self.db.one("SELECT 1 FROM clips WHERE parent_clip_id = ? AND deleted_at IS NULL", (clip_id,)):
                raise ServiceError("klip ini punya lanjutan (extend); hapus lanjutannya dulu", 409)
            self.films.detach_clip(clip_id)   # menolak (409) sebelum mengubah apa pun bila ada film yang sedang dirender
            self._unlink(clip["path"]); self._unlink(clip["merged_path"])
            self.db.update("clips", clip_id, {"deleted_at": now(), "path": None, "merged_path": None})

    def delete_character(self, character_id: str, ws: str = DEFAULT_WS) -> None:
        with self._lock:
            self.get_character(character_id, ws)
            voice_files = [r["path"] for r in self.db.all("SELECT path FROM voice_versions WHERE character_id = ?", (character_id,))]
            with self.db.transaction() as tx:   # adegan tetap ada; hanya pemerannya yang dilepas
                tx.execute("UPDATE scenes SET prompt = NULL WHERE id IN (SELECT scene_id FROM scene_cast WHERE character_id = ?)", (character_id,))
                tx.execute("DELETE FROM voice_versions WHERE character_id = ?", (character_id,))
                tx.execute("DELETE FROM scene_cast WHERE character_id = ?", (character_id,))
                tx.execute("DELETE FROM film_characters WHERE character_id = ?", (character_id,))
                tx.execute("DELETE FROM outfits WHERE character_id = ?", (character_id,))
                tx.execute("DELETE FROM character_images WHERE character_id = ?", (character_id,))
                tx.execute("DELETE FROM characters WHERE id = ?", (character_id,))
            for stored in voice_files:
                self._unlink(stored)

    def bulk_delete(self, image_ids: list[str], clip_ids: list[str], character_ids: list[str],
                    ws: str = DEFAULT_WS) -> dict:
        """Hapus banyak item lewat delete_* satuan (aturan penolakan sama). Kunci per item, bukan per batch."""
        image_ids, clip_ids, character_ids = (list(dict.fromkeys(x)) for x in (image_ids, clip_ids, character_ids))
        if len(image_ids) + len(clip_ids) + len(character_ids) == 0:
            raise ServiceError("tidak ada item yang dipilih")
        depth = {}
        for cid in clip_ids:   # rantai extend: dari yang terdalam, supaya induk tidak ditolak oleh anaknya sendiri
            row = self.db.one("SELECT chain_depth FROM clips WHERE id = ? AND deleted_at IS NULL AND workspace_id = ?", (cid, ws))
            depth[cid] = row["chain_depth"] if row else 0
        clip_ids.sort(key=lambda c: -depth[c])
        deleted = {"images": 0, "clips": 0, "characters": 0}
        skipped, failed = 0, []
        for kind, key, ids, fn in (("clip", "clips", clip_ids, self.delete_clip),
                                   ("character", "characters", character_ids, self.delete_character),
                                   ("image", "images", image_ids, self.delete_image)):
            for item in ids:
                try:
                    fn(item, ws)
                    deleted[key] += 1
                except ServiceError as exc:
                    if exc.status == 404:
                        skipped += 1   # sudah tidak ada (atau milik workspace lain): bukan kegagalan
                    else:
                        failed.append({"type": kind, "id": item, "reason": str(exc)})
        return {"deleted": deleted, "skipped": skipped, "failed": failed}

    def extend_clip(self, clip_id: str, prompt: str, model: str, ws: str = DEFAULT_WS, **kw) -> dict:
        parent = self.get_clip(clip_id, ws)
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
        frame = self._save_image(png, w, h, kind="frame", ws=ws)
        try:
            return self.create_clip(image_id=frame["id"], prompt=prompt, model=model,
                                    parent_clip_id=clip_id, chain_depth=depth, ws=ws, **kw)
        except ServiceError:   # penolakan (biaya, validasi) tidak boleh meninggalkan frame yatim
            self.db.execute("DELETE FROM images WHERE id = ?", (frame["id"],))
            self.storage.resolve(frame["path"]).unlink(missing_ok=True)
            raise

    def merge_chain(self, clip_id: str, ws: str = DEFAULT_WS) -> dict:
        chain, cur = [], self.get_clip(clip_id, ws)
        while cur:
            if cur["status"] != "completed" or not cur["path"]:
                raise ServiceError("ada klip dalam rantai yang belum selesai", 409)
            chain.append(cur)
            cur = self.get_clip(cur["parent_clip_id"], ws) if cur["parent_clip_id"] else None
        chain.reverse()
        out = self.storage.new_path(".mp4")
        try:
            media.merge_videos([self.storage.resolve(c["path"]) for c in chain], out)
        except media.MediaError as exc:
            out.unlink(missing_ok=True)
            raise ServiceError(f"gagal menggabungkan: {exc}", 500) from exc
        self.db.update("clips", clip_id, {"merged_path": str(out), "updated_at": now()})
        return self.get_clip(clip_id, ws)

    # ---------- polling ----------
    def poll_once(self) -> None:
        for clip in self.db.all("SELECT * FROM clips WHERE status IN ('submitted','in_progress')"):
            try:
                self._poll_clip(clip)
                if self.get_clip(clip["id"], None)["status"] not in ACTIVE:   # poller lintas workspace: tanpa batas
                    self._release_published(clip["id"])
            except OpenRouterError as exc:
                # error jaringan sementara: biarkan, coba lagi di siklus berikut
                self.db.update("clips", clip["id"], {"error": str(exc), "updated_at": now()})

    def _release_published(self, clip_id: str) -> None:
        row = self.db.one("SELECT params FROM clips WHERE id = ?", (clip_id,))
        params = json.loads(row["params"]) if row else {}
        for key in [params.get("published_key"), *params.get("published_keys", [])]:   # published_keys: Storyboard v2 (audio/previs)
            if key:
                self.public.delete(key)

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
            info = media.probe(path)  # validasi file benar-benar video
        except (OpenRouterError, media.MediaError) as exc:
            self.db.update("clips", clip_id, {"status": "failed_download", "error": str(exc)[:500],
                                              "updated_at": now()})
            return
        self.db.update("clips", clip_id, {"status": "completed", "path": str(path), "error": None,
                                          "duration": info["duration"], "updated_at": now()})

    def retry_download(self, clip_id: str, ws: str = DEFAULT_WS) -> dict:
        clip = self.get_clip(clip_id, ws)
        if clip["status"] != "failed_download":
            raise ServiceError("klip tidak dalam status failed_download", 409)
        self._download(clip_id, clip["remote_job_id"])
        return self.get_clip(clip_id, ws)

    # ---------- worker ----------
    def start(self) -> None:
        # job yang masih aktif saat startup otomatis dilanjutkan oleh loop yang sama
        self.films.recover()   # render film yang terputus ditandai gagal, bukan "rendering" selamanya
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
    # Lembar karakter (plan 19): SATU gambar berisi beberapa sudut berdampingan, bukan beberapa foto terpisah.
    SHEET_ANGLES = ("front view", "three-quarter view", "side profile view", "back view")
    SHEET_PROMPT = (
        "Character turnaround reference sheet, ONE single image: the same character as in the reference image shown "
        f"{len(SHEET_ANGLES)} times side by side in one row, left to right: " + ", ".join(SHEET_ANGLES) + ". "
        "Full body, head to toe, standing in a neutral pose, same height and scale in every panel, evenly spaced, "
        "plain light-gray background. Keep the face, hairstyle, clothing, accessories and colors exactly identical in every panel. "
        "No text, no labels, no panel borders.")
    SHEET_RATIO = "16:9"   # lebar supaya semua panel muat; dipakai bila user tidak memilih dan model mendukung

    def _sheet_options(self, model: str, aspect_ratio: str | None, quality: str | None) -> dict:
        options = {k: v for k, v in {"aspect_ratio": aspect_ratio, "quality": quality}.items() if v}
        if "aspect_ratio" not in options:
            options.update(self.scenes._aspect_option(model, self.SHEET_RATIO))
        return options

    def create_character(self, name: str, description: str, source_image_id: str, ws: str = DEFAULT_WS) -> dict:
        if not name.strip() or not description.strip():
            raise ServiceError("nama dan deskripsi karakter wajib diisi")
        if len(name) > 80 or len(description) > 2000:
            raise ServiceError("nama maks 80 dan deskripsi maks 2000 karakter")
        if "[" in name or "]" in name:
            raise ServiceError("nama karakter tidak boleh memuat [ atau ] (dipakai untuk mention di naskah)", 422)
        self.get_image(source_image_id, ws)
        row = {"id": uuid.uuid4().hex, "name": name.strip(), "description": description.strip(),
               "source_image_id": source_image_id, "created_at": now(), "workspace_id": ws}
        self.db.insert("characters", row)
        self.db.insert("character_images", {"character_id": row["id"], "image_id": source_image_id, "label": "source"})
        return row

    def portrait_plan(self, model: str, description: str) -> dict:
        """Satu sumber untuk estimasi dan pembuatan potret karakter dari deskripsi (plan 16)."""
        description = (description or "").strip()
        if not description:
            raise ServiceError("deskripsi karakter wajib diisi untuk membuat gambar", 422)
        if len(description) > 2000:
            raise ServiceError("deskripsi maks 2000 karakter", 422)
        options = self.scenes._aspect_option(model, "3:4")
        self._validate_image_params(model, options, 0)
        return {"options": options, "prompt": sceneprompt.portrait_prompt(description)}

    def create_portrait(self, description: str, model: str, ws: str = DEFAULT_WS, confirmed_cost: float | None = None,
                        accept_unknown_cost: bool = False) -> dict:
        """Buat SATU gambar potret karakter (teks ke gambar) dan simpan di library sebagai kind=portrait. Tidak membuat karakter."""
        with self._lock:
            plan = self.portrait_plan(model, description)
            est = self.estimate_image_job(model, n_inputs=0)
            self.authorize(est, confirmed_cost, accept_unknown_cost)
            try:
                resp = self.client.generate_image(model, plan["prompt"], **plan["options"])
            except OpenRouterError as exc:
                raise ServiceError(str(exc), 502) from exc
            return self._store_edit_results(resp, None, plan["prompt"], model, est, "portrait", ws)[0]

    def get_character(self, character_id: str, ws: str | None = DEFAULT_WS) -> dict:
        sql, args = "SELECT * FROM characters WHERE id = ?", [character_id]
        if ws is not None:
            sql, args = sql + " AND workspace_id = ?", [*args, ws]
        row = self.db.one(sql, tuple(args))
        if not row:
            raise ServiceError("karakter tidak ditemukan", 404)
        return row

    def character_images(self, character_id: str) -> list[dict]:
        return self.db.all("SELECT image_id, label FROM character_images WHERE character_id = ? "
                           "ORDER BY rowid", (character_id,))

    def add_character_image(self, character_id: str, image_id: str, label: str = "custom", ws: str = DEFAULT_WS) -> None:
        self.get_character(character_id, ws)
        self.get_image(image_id, ws)
        self.db.execute("INSERT OR REPLACE INTO character_images (character_id, image_id, label) VALUES (?, ?, ?)",
                        (character_id, image_id, label[:30]))

    def estimate_sheet(self, model: str, aspect_ratio: str | None = None, quality: str | None = None) -> pricing.Estimate:
        """Satu gambar (plan 19)."""
        self._validate_image_params(model, self._sheet_options(model, aspect_ratio, quality), 1)
        return self.estimate_image_job(model, n_inputs=1)

    def generate_sheet(self, character_id: str, model: str, aspect_ratio: str | None = None,
                       quality: str | None = None, confirmed_cost: float | None = None,
                       accept_unknown_cost: bool = False, ws: str = DEFAULT_WS) -> list[dict]:
        char = self.get_character(character_id, ws)
        options = self._sheet_options(model, aspect_ratio, quality)
        self._validate_image_params(model, options, 1)
        with self._lock:
            est = self.estimate_sheet(model, aspect_ratio, quality)
            self.authorize(est, confirmed_cost, accept_unknown_cost)
            full = f"{self.SHEET_PROMPT} Character details: {char['description']}"
            images = self._run_edit(char["source_image_id"], full, model, [], options, est, kind="sheet", ws=ws)
            for img in images:
                self.add_character_image(character_id, img["id"], "sheet", ws)
            return images
