import json
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import StrictBool, BaseModel, ConfigDict, Field, model_validator

from . import editprompt, media, textai
from .config import Settings
from .db import Database
from .openrouter import OpenRouterClient
from .publicmedia import NoPublicMedia, S3PublicMedia, TunnelPublicMedia
from .service import DEFAULT_WS, ServiceError, Studio
from .storage import Storage


class Confirm(BaseModel):
    confirmed_cost: float | None = None      # nilai `high` estimasi yang dilihat user
    accept_unknown_cost: bool = False


class ClipIn(Confirm):
    image_id: str
    prompt: str = Field(max_length=4000)
    model: str
    duration: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    generate_audio: bool = False
    idempotency_key: str | None = Field(default=None, max_length=100)
    last_image_id: str | None = None
    negative_prompt: str | None = Field(default=None, max_length=2000)


class ExtendIn(Confirm):
    prompt: str = Field(max_length=4000)
    model: str
    duration: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    generate_audio: bool = False
    idempotency_key: str | None = Field(default=None, max_length=100)
    negative_prompt: str | None = Field(default=None, max_length=2000)


class SettingsIn(BaseModel):   # plan 18: pengaturan proyek; field yang tidak dikirim tidak diubah
    video_model: str | None = None
    video_resolution: str | None = None
    aspect_ratio: str | None = None
    generate_audio: bool | None = None
    image_model: str | None = None
    style: str | None = Field(default=None, max_length=500)
    genre: str | None = Field(default=None, max_length=80)
    confirm_sync: bool = False


class WorkspaceIn(BaseModel):
    name: str = Field(max_length=200)   # panjang sebenarnya (maks 60) dicek service agar pesannya jelas


class CopyIn(BaseModel):
    image_ids: list[str] = Field(default=[], max_length=100)
    character_ids: list[str] = Field(default=[], max_length=100)


class BulkDeleteIn(BaseModel):
    image_ids: list[str] = []
    clip_ids: list[str] = []
    character_ids: list[str] = []

    @model_validator(mode="after")
    def _cap(self):
        if len(self.image_ids) + len(self.clip_ids) + len(self.character_ids) > 200:
            raise ValueError("maksimum 200 item per permintaan")
        return self


class FilmIn(BaseModel):
    title: str = Field(max_length=120)
    number: int | None = None
    synopsis: str = Field(default="", max_length=4000)


class FilmUpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    number: int | None = None
    synopsis: str | None = Field(default=None, max_length=4000)
    aspect_ratio: str | None = Field(default=None, max_length=10)
    clip_ids: list[str] | None = None   # sudah tidak dipakai (plan 08): ditolak dengan pesan jelas
    script: str | None = Field(default=None, max_length=25000)   # naskah episode (plan 15); batas sebenarnya dicek script.clean_script
    previs_skipped: bool | None = None


class SceneAddIn(BaseModel):
    after_scene_id: str | None = None
    inherit: bool = True
    clip_id: str | None = None


class CastIn(BaseModel):
    character_id: str
    outfit_id: str | None = None
    action: str = Field(default="", max_length=1000)


class SceneUpdateIn(BaseModel):   # hanya field yang dikirim yang diubah (model_dump(exclude_unset=True))
    model_config = ConfigDict(extra="forbid")   # salah ketik nama field = 422, bukan diabaikan diam-diam
    location_id: str | None = None
    time_of_day: str | None = Field(default=None, max_length=500)
    camera: str | None = Field(default=None, max_length=500)
    dialogue: str | None = Field(default=None, max_length=5000)
    extra_prompt: str | None = Field(default=None, max_length=5000)
    keyframe_image_id: str | None = None
    clip_id: str | None = None
    cast: list[CastIn] | None = Field(default=None, max_length=20)
    planned_seconds: int | None = None
    blockout: dict | None = None   # susunan 3D (plan 14); divalidasi blockout.clean
    blockout_image_id: str | None = None
    start_from_prev: StrictBool | None = None   # plan 18 Revisi 9: mulai dari frame akhir adegan sebelumnya


class TextJobIn(Confirm):   # pekerjaan AI teks: model dipilih per permintaan (plan 17); kosong = bawaan server
    model: str | None = Field(default=None, max_length=120)


class ScenePromptIn(BaseModel):   # plan 18 Revisi 8
    prompt: str = Field(max_length=4000)


class ReviseIn(TextJobIn):   # plan 18 Revisi 6
    instruction: str = Field(max_length=500)


class BeatsIn(BaseModel):   # plan 18: penggantian seluruh beat adegan
    beats: list[dict]
    note: str = ""


class RestoreBeatsIn(BaseModel):
    version_id: str


MAX_VOICE_UPLOAD = 20 * 1024 * 1024


class ResolveIn(BaseModel):
    layout: dict | None = None


class PortraitIn(Confirm):   # potret karakter dari deskripsi (plan 16); nama sengaja tidak ikut
    description: str = Field(max_length=2000)
    model: str


class CastSetIn(BaseModel):   # pemeran/latar episode (plan 15)
    character_ids: list[str] = Field(default=[], max_length=100)
    location_ids: list[str] = Field(default=[], max_length=100)
    release: bool = False   # lepas juga dari adegan yang masih memakainya


class SplitApplyIn(BaseModel):
    scenes: list[dict] = Field(max_length=100)
    mode: str = "append"


class SceneOrderIn(BaseModel):
    scene_ids: list[str] = Field(max_length=100)


class SceneIdsIn(BaseModel):
    scene_ids: list[str] = Field(min_length=1, max_length=200)


class LocationIn(BaseModel):
    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=2000)
    image_id: str | None = None


class LocationUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    image_id: str | None = None


class OutfitIn(BaseModel):
    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=2000)
    image_id: str | None = None


class EstimateIn(BaseModel):
    kind: str = Field(pattern="^(video|image_edit|character_sheet|motion|motion_anchor|scene_keyframe|scene_video|scene_blockout|scene_beats|scene_revise|script_revise|scene_prompt_revise|scene_previs_video|storyboard_video|episode_script|episode_split|character_portrait|location_image)$")
    model: str
    duration: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    generate_audio: bool = False
    reference_count: int = Field(default=0, ge=0, le=20)   # gambar referensi tambahan (edit foto)
    quality: str | None = None
    use_previs: bool = False             # storyboard_video: sertakan video previs 3D sebagai referensi
    mode: str | None = None              # motion: flux_edit | anchor_edit | reference
    reference_id: str | None = None
    # image_edit berbasis id (plan 06): server menghitung daftar gambar input dengan plan_edit, sama seperti saat generate
    source_image_id: str | None = None
    character_id: str | None = None
    pose_image_id: str | None = None
    pose_mode: str = "sketch"
    expression_image_id: str | None = None
    reference_image_ids: list[str] = []
    pose_text: str | None = Field(default=None, max_length=200)
    expression_text: str | None = Field(default=None, max_length=200)
    # adegan (plan 08): server menghitung daftar gambar input dengan Scenes.keyframe_plan, sama seperti saat generate
    scene_id: str | None = None
    location_id: str | None = None
    film_id: str | None = None   # episode_script / episode_split (plan 15)
    description: str | None = Field(default=None, max_length=2000)   # character_portrait (plan 16)


class SceneKeyframeIn(Confirm):
    model: str


class SceneVideoIn(Confirm):
    model: str
    duration: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    generate_audio: bool = False
    idempotency_key: str | None = Field(default=None, max_length=100)


class StoryboardVideoIn(Confirm):
    prompt: str | None = Field(default=None, max_length=4000)   # prompt hasil sunting user; kosong = pakai rakitan server
    use_previs: bool = False
    idempotency_key: str | None = Field(default=None, max_length=100)


class LocationImageIn(Confirm):
    model: str


class MotionIn(Confirm):
    mode: str
    model: str
    reference_id: str
    prompt: str = Field(max_length=4000)
    character_id: str | None = None
    image_ids: list[str] = []
    anchor_image_id: str | None = None
    subject_text: str | None = Field(default=None, max_length=1000)   # flux_edit: menggantikan deskripsi baku karakter
    duration: int | None = None
    resolution: str | None = Field(default=None, max_length=20)
    aspect_ratio: str | None = Field(default=None, max_length=20)
    generate_audio: bool = False
    idempotency_key: str | None = Field(default=None, max_length=100)


class TrimIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    start: float
    end: float


class AnchorIn(Confirm):
    reference_id: str
    character_id: str
    model: str
    quality: str | None = Field(default=None, max_length=20)
    aspect_ratio: str | None = Field(default=None, max_length=20)


class CharacterIn(BaseModel):
    name: str = Field(max_length=80)
    description: str = Field(max_length=2000)
    source_image_id: str


class SheetIn(Confirm):
    model: str
    aspect_ratio: str | None = Field(default=None, max_length=20)
    quality: str | None = Field(default=None, max_length=20)


class AddImageIn(BaseModel):
    image_id: str
    label: str = Field(default="custom", max_length=30)


class EditIn(Confirm):
    prompt: str = Field(max_length=4000)
    model: str
    reference_image_ids: list[str] = []
    resolution: str | None = Field(default=None, max_length=20)
    aspect_ratio: str | None = Field(default=None, max_length=20)
    quality: str | None = Field(default=None, max_length=20)
    character_id: str | None = None
    pose_image_id: str | None = None
    pose_mode: str = "sketch"            # sketch | original
    expression_image_id: str | None = None
    pose_text: str | None = Field(default=None, max_length=200)
    expression_text: str | None = Field(default=None, max_length=200)


def create_app(settings: Settings | None = None, client: OpenRouterClient | None = None,
               public=None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.data_dir / "studio.db")
    storage = Storage(settings.data_dir / "media")
    client = client or OpenRouterClient(settings.api_key, settings.base_url)
    if public is None:
        public = (S3PublicMedia(settings.s3_endpoint_url, settings.s3_bucket, settings.s3_access_key_id,
                                settings.s3_secret_access_key, settings.s3_region, settings.public_url_ttl)
                  if settings.s3_bucket and settings.s3_access_key_id and settings.s3_secret_access_key
                  else TunnelPublicMedia(settings.public_url_ttl)   # plan 10: quick tunnel cloudflared tanpa akun
                  if settings.public_tunnel == "cloudflared" and shutil.which("cloudflared")
                  else NoPublicMedia())
    studio = Studio(settings, db, storage, client, public)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        studio.public.cleanup(86400)   # sisa objek publik yang tak sempat dibersihkan
        studio.start()
        yield
        studio.stop()
        getattr(studio.public, "close", lambda: None)()   # matikan tunnel (bila ada)

    app = FastAPI(title="AI Animation Studio", lifespan=lifespan)
    app.state.studio = studio

    @app.exception_handler(ServiceError)
    async def service_error(_: Request, exc: ServiceError):
        return JSONResponse({"detail": str(exc), **exc.extra}, status_code=exc.status)

    def get_studio() -> Studio:
        return studio

    def get_ws(response: Response, x_workspace_id: str | None = Header(default=None)) -> str:
        """Workspace aktif dari header; tanpa header = Utama (klien lama, tes, skrip). Hilang/diarsip -> 404 workspace_missing.
        Server menggemakan id yang dipakai agar frontend bisa memastikan request tidak salah workspace."""
        ws = x_workspace_id or DEFAULT_WS
        studio.workspaces.get(ws)
        response.headers["X-Workspace-Id"] = ws
        return ws

    WS = Annotated[str, Depends(get_ws)]

    def public_clip(c: dict) -> dict:
        return {k: v for k, v in c.items() if k not in ("path", "merged_path")} | {
            "has_file": bool(c["path"]), "has_merged": bool(c["merged_path"]),
            **{k: json.loads(c["params"] or "{}").get(k) for k in ("last_image_id", "negative_prompt")}}

    def public_image(i: dict) -> dict:
        return {k: v for k, v in i.items() if k != "path"}

    @app.get("/api/health")
    def health():
        return {"ffmpeg": media.ffmpeg_available(), "api_key": bool(settings.api_key),
                "spent_today": studio.db.spent_today(), "daily_budget": settings.daily_budget_usd,
                "max_per_job": settings.max_cost_per_job,
                "public_media": not isinstance(studio.public, NoPublicMedia),
                "max_reference_seconds": settings.max_reference_seconds}

    @app.post("/api/estimate")
    def estimate(body: EstimateIn, ws: WS, s: Studio = Depends(get_studio)):
        """Perkiraan biaya tanpa efek samping; parameter divalidasi seperti saat generate."""
        n_inputs = None   # jumlah gambar input untuk image_edit berbasis id (ditampilkan UI)
        if body.kind == "motion_anchor":
            if not body.character_id:
                raise ServiceError("motion_anchor membutuhkan character_id")
            est = s.estimate_image_job(body.model, n_inputs=1 + len(s.motion.anchor_sheet(body.character_id, ws)))
        elif body.kind == "motion":
            est = s.motion.estimate(body.mode or "", body.model, body.reference_id or "", duration=body.duration,
                                    resolution=body.resolution, aspect_ratio=body.aspect_ratio,
                                    generate_audio=body.generate_audio, ws=ws)
        elif body.kind == "character_sheet":
            est = s.estimate_sheet(body.model, body.aspect_ratio, body.quality)
        elif body.kind == "video":
            params = {k: v for k, v in {"duration": body.duration, "resolution": body.resolution,
                                        "aspect_ratio": body.aspect_ratio}.items() if v is not None}
            params["generate_audio"] = body.generate_audio
            s._validate_video_params(body.model, params)
            est = s.estimate_video_job(body.model, params)
        elif body.kind == "location_image":
            s.scenes.location_plan(body.location_id or "", body.model, ws)
            est = s.estimate_image_job(body.model, n_inputs=0)
        elif body.kind == "scene_keyframe":
            n_inputs = len(s.scenes.keyframe_plan(body.scene_id or "", body.model, ws)["inputs"])
            est = s.estimate_image_job(body.model, n_inputs=n_inputs)
        elif body.kind == "scene_prompt_revise":
            est = s.sprompt.revise_estimate(body.scene_id or "", ws, body.model)
        elif body.kind == "script_revise":
            est = s.journey.script_revise_estimate(body.film_id or "", ws, body.model)
        elif body.kind == "scene_revise":
            est = s.beats.revise_estimate(body.scene_id or "", ws, body.model)
        elif body.kind == "scene_beats":
            est = s.beats.ai_estimate(body.scene_id or "", ws, body.model)
        elif body.kind == "scene_blockout":
            est = s.scenes.blockout_estimate(body.scene_id or "", ws, body.model)
        elif body.kind == "character_portrait":
            s.portrait_plan(body.model, body.description or "")
            est = s.estimate_image_job(body.model, n_inputs=0)
        elif body.kind == "episode_script":
            est = s.journey.script_estimate(body.film_id or "", ws, body.model)
        elif body.kind == "episode_split":
            est = s.journey.split_estimate(body.film_id or "", ws, body.model)
        elif body.kind == "scene_previs_video":
            plan = s.scenes.previs_video_plan(body.scene_id or "", ws)
            est = s.motion.estimate("reference", body.model, plan["ref_id"], duration=body.duration, resolution=body.resolution,
                                    aspect_ratio=s.scenes.video_aspect(plan["film"]["aspect_ratio"], body.model, body.aspect_ratio),
                                    generate_audio=body.generate_audio, ws=ws)
        elif body.kind == "storyboard_video":
            est = s.sbvideo.estimate(s.sbvideo.plan(body.scene_id or "", ws, use_audio=False, use_previs=body.use_previs))
        elif body.kind == "scene_video":
            plan = s.scenes.video_plan(body.scene_id or "", ws)
            params = {k: v for k, v in {"duration": body.duration, "resolution": body.resolution,
                                        "aspect_ratio": s.scenes.video_aspect(plan["film"]["aspect_ratio"], body.model, body.aspect_ratio)}.items()
                      if v is not None}
            params["generate_audio"] = body.generate_audio
            s._validate_video_params(body.model, params)
            est = s.estimate_video_job(body.model, params)
        else:
            options = {k: v for k, v in {"resolution": body.resolution, "aspect_ratio": body.aspect_ratio,
                                         "quality": body.quality}.items() if v}
            if body.source_image_id:
                plan = s.plan_edit(body.source_image_id, body.model, character_id=body.character_id,
                                   pose_image_id=body.pose_image_id, pose_mode=body.pose_mode,
                                   expression_image_id=body.expression_image_id, reference_ids=body.reference_image_ids,
                                   pose_text=body.pose_text, expression_text=body.expression_text, ws=ws)
                n_inputs = len(plan.entries)
            else:   # klien lama: hanya jumlah referensi
                n_inputs = 1 + body.reference_count
            s._validate_image_params(body.model, options, n_inputs)
            est = s.estimate_image_job(body.model, n_inputs=n_inputs, resolution=body.resolution)
        state = s.budget_state()
        blocked = None
        if body.kind == "storyboard_video":   # Storyboard v2 tidak diblokir batas per job/harian (plan 18 Revisi 2); konfirmasi tetap wajib
            pass
        elif est.confidence != "unknown" and est.high > state["max_per_job"]:
            blocked = f"melebihi batas per job ${state['max_per_job']:.2f}"
        elif state["committed_today"] + est.high > state["daily_budget"]:
            blocked = "melebihi batas harian"
        return {**est.as_dict(), **state, "blocked": blocked, **({"inputs": n_inputs} if n_inputs else {})}

    @app.get("/api/catalog/video")
    def video_catalog(refresh: bool = False, s: Studio = Depends(get_studio)):
        return s.video_catalog(refresh)

    @app.get("/api/catalog/image")
    def image_catalog(refresh: bool = False, s: Studio = Depends(get_studio)):
        return s.image_catalog(refresh)

    @app.get("/api/models/video")
    def video_models(s: Studio = Depends(get_studio)):
        return s.video_models()

    @app.get("/api/models/text")
    def text_models(s: Studio = Depends(get_studio)):
        """Model teks yang layak dipilih untuk fitur AI (disaring, di-cache 5 menit) dan bawaan server (plan 17)."""
        return {"default": textai.default_model(s), "models": textai.catalog(s)}

    @app.get("/api/models/image")
    def image_models(s: Studio = Depends(get_studio)):
        return s.image_models()

    @app.post("/api/images")
    async def upload_image(ws: WS, file: UploadFile = File(...), s: Studio = Depends(get_studio)):
        data = await file.read(s.s.max_upload_bytes + 1)
        return public_image(s.add_upload(data, ws))

    @app.get("/api/images")
    def list_images(ws: WS, s: Studio = Depends(get_studio)):
        # origin_workspace: nama workspace asal bila gambar ini salinan (jejak asal tidak bisa dibuka lintas workspace)
        rows = s.db.all(
            "SELECT i.*, w.name AS origin_workspace FROM images i LEFT JOIN images o ON o.id = i.origin_image_id "
            "LEFT JOIN workspaces w ON w.id = o.workspace_id "
            "WHERE i.deleted_at IS NULL AND i.workspace_id = ? ORDER BY i.created_at DESC LIMIT 200", (ws,))
        return [public_image(i) for i in rows]

    @app.delete("/api/images/{image_id}")
    def delete_image(image_id: str, ws: WS, s: Studio = Depends(get_studio)):
        s.delete_image(image_id, ws)
        return {"ok": True}

    @app.delete("/api/clips/{clip_id}")
    def delete_clip(clip_id: str, ws: WS, s: Studio = Depends(get_studio)):
        s.delete_clip(clip_id, ws)
        return {"ok": True}

    @app.delete("/api/characters/{character_id}")
    def delete_character(character_id: str, ws: WS, s: Studio = Depends(get_studio)):
        s.delete_character(character_id, ws)
        return {"ok": True}

    @app.post("/api/bulk-delete")
    def bulk_delete(data: BulkDeleteIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.bulk_delete(data.image_ids, data.clip_ids, data.character_ids, ws)

    @app.get("/api/images/{image_id}/sketch")
    def image_sketch(image_id: str, s: Studio = Depends(get_studio)):
        """Pratinjau sketsa pose: byte yang sama dengan yang dikirim ke model (editprompt.make_pose_sketch)."""
        data = s.storage.resolve(s.get_image(image_id, None)["path"]).read_bytes()   # berkas: tanpa batas workspace (plan 07 grill 1)
        return Response(editprompt.make_pose_sketch(data), media_type="image/png")

    @app.get("/api/images/{image_id}/file")
    def image_file(image_id: str, s: Studio = Depends(get_studio)):
        return FileResponse(s.storage.resolve(s.get_image(image_id, None)["path"]), media_type="image/png")

    @app.post("/api/images/{image_id}/edit")
    def edit_image(image_id: str, body: EditIn, ws: WS, s: Studio = Depends(get_studio)):
        return [public_image(i) for i in s.edit_image(
            image_id, body.prompt, body.model, body.reference_image_ids,
            resolution=body.resolution, aspect_ratio=body.aspect_ratio, quality=body.quality,
            confirmed_cost=body.confirmed_cost, accept_unknown_cost=body.accept_unknown_cost,
            character_id=body.character_id, pose_image_id=body.pose_image_id, pose_mode=body.pose_mode,
            expression_image_id=body.expression_image_id, pose_text=body.pose_text, expression_text=body.expression_text,
            ws=ws)]

    def public_character(c: dict) -> dict:
        return {**c, "images": s_images(c["id"]), "outfits": studio.scenes.list_outfits(c["id"], c["workspace_id"])}

    def s_images(character_id: str) -> list[dict]:
        return studio.character_images(character_id)

    @app.post("/api/characters")
    def create_character(body: CharacterIn, ws: WS, s: Studio = Depends(get_studio)):
        return public_character(s.create_character(body.name, body.description, body.source_image_id, ws))

    @app.get("/api/characters")
    def list_characters(ws: WS, s: Studio = Depends(get_studio)):
        return [public_character(c) for c in s.db.all(
            "SELECT * FROM characters WHERE workspace_id = ? ORDER BY created_at DESC", (ws,))]

    @app.get("/api/characters/{character_id}")
    def get_character(character_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return public_character(s.get_character(character_id, ws))

    @app.post("/api/characters/portrait")
    def character_portrait(body: PortraitIn, ws: WS, s: Studio = Depends(get_studio)):
        """Satu gambar potret dari deskripsi (tanpa referensi); karakter dibuat terpisah lewat POST /api/characters."""
        return public_image(s.create_portrait(body.description, body.model, ws, body.confirmed_cost, body.accept_unknown_cost))

    @app.post("/api/characters/{character_id}/images")
    def add_character_image(character_id: str, body: AddImageIn, ws: WS, s: Studio = Depends(get_studio)):
        s.add_character_image(character_id, body.image_id, body.label, ws)
        return public_character(s.get_character(character_id, ws))

    @app.post("/api/characters/{character_id}/sheet")
    def character_sheet(character_id: str, body: SheetIn, ws: WS, s: Studio = Depends(get_studio)):
        s.generate_sheet(character_id, body.model, body.aspect_ratio, body.quality,
                         body.confirmed_cost, body.accept_unknown_cost, ws=ws)
        return public_character(s.get_character(character_id, ws))

    @app.post("/api/references")
    async def upload_reference(ws: WS, file: UploadFile = File(...), s: Studio = Depends(get_studio)):
        tmp = s.storage.new_path(".upload")
        size = 0
        try:
            with open(tmp, "wb") as fh:   # streaming ke disk, bukan memuat seluruh video ke RAM
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > s.s.max_video_upload_bytes:
                        raise ServiceError("file video terlalu besar", 413)
                    fh.write(chunk)
            return s.motion.add_upload(tmp, ws)
        finally:
            tmp.unlink(missing_ok=True)

    @app.post("/api/references/from-clip/{clip_id}")
    def reference_from_clip(clip_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return s.motion.add_from_clip(clip_id, ws)

    @app.post("/api/references/{ref_id}/trim")
    def trim_reference(ref_id: str, body: TrimIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.motion.trim(ref_id, body.start, body.end, ws)

    @app.get("/api/references")
    def list_references(ws: WS, s: Studio = Depends(get_studio)):
        return [{k: v for k, v in r.items() if k != "path"} for r in
                s.db.all("SELECT * FROM refs WHERE workspace_id = ? ORDER BY created_at DESC LIMIT 100", (ws,))]

    @app.get("/api/references/{ref_id}/file")
    def reference_file(ref_id: str, s: Studio = Depends(get_studio)):
        return FileResponse(s.storage.resolve(s.motion.get_ref(ref_id, None)["path"]), media_type="video/mp4")

    @app.post("/api/motion/anchor")
    def motion_anchor(body: AnchorIn, ws: WS, s: Studio = Depends(get_studio)):
        return public_image(s.motion.make_anchor(body.reference_id, body.character_id, body.model,
                                                 quality=body.quality, aspect_ratio=body.aspect_ratio,
                                                 confirmed_cost=body.confirmed_cost,
                                                 accept_unknown_cost=body.accept_unknown_cost, ws=ws))

    @app.post("/api/motion")
    def motion(body: MotionIn, ws: WS, s: Studio = Depends(get_studio)):
        data = body.model_dump()
        return public_clip(s.motion.create(ref_id=data.pop("reference_id"), **data, ws=ws))

    @app.post("/api/clips")
    def create_clip(body: ClipIn, ws: WS, s: Studio = Depends(get_studio)):
        return public_clip(s.create_clip(**body.model_dump(), ws=ws))

    @app.get("/api/clips")
    def list_clips(ws: WS, s: Studio = Depends(get_studio)):
        return [public_clip(c) for c in s.db.all(
            "SELECT * FROM clips WHERE deleted_at IS NULL AND workspace_id = ? ORDER BY created_at DESC LIMIT 200", (ws,))]

    @app.get("/api/clips/{clip_id}")
    def get_clip(clip_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return public_clip(s.get_clip(clip_id, ws))

    @app.get("/api/clips/{clip_id}/file")
    def clip_file(clip_id: str, s: Studio = Depends(get_studio)):
        clip = s.get_clip(clip_id, None)   # berkas: tanpa batas workspace (plan 07 grill 1)
        if not clip["path"]:
            raise HTTPException(404, "file belum tersedia")
        return FileResponse(s.storage.resolve(clip["path"]), media_type="video/mp4")

    @app.post("/api/clips/{clip_id}/extend")
    def extend_clip(clip_id: str, body: ExtendIn, ws: WS, s: Studio = Depends(get_studio)):
        return public_clip(s.extend_clip(clip_id, ws=ws, **body.model_dump()))

    @app.post("/api/clips/{clip_id}/merge")
    def merge_clip(clip_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return public_clip(s.merge_chain(clip_id, ws))

    @app.get("/api/clips/{clip_id}/merged")
    def merged_file(clip_id: str, s: Studio = Depends(get_studio)):
        clip = s.get_clip(clip_id, None)
        if not clip["merged_path"]:
            raise HTTPException(404, "belum digabung")
        return FileResponse(s.storage.resolve(clip["merged_path"]), media_type="video/mp4")

    @app.post("/api/clips/{clip_id}/retry-download")
    def retry_download(clip_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return public_clip(s.retry_download(clip_id, ws))

    # ---------- storyboard / film (plan 05) ----------
    @app.get("/api/films")
    def list_films(ws: WS, s: Studio = Depends(get_studio)):
        return s.films.list_all(ws)

    @app.post("/api/films")
    def create_film(body: FilmIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.films.create(body.title, ws, body.number, body.synopsis)

    @app.get("/api/films/{film_id}")
    def get_film(film_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return s.films.detail(film_id, ws)

    @app.put("/api/films/{film_id}")
    def update_film(film_id: str, body: FilmUpdateIn, ws: WS, s: Studio = Depends(get_studio)):
        if body.clip_ids is not None:
            raise HTTPException(422, "clip_ids tidak dipakai lagi; tambah adegan lewat POST /api/films/{id}/scenes")
        return s.films.update(film_id, body.title, ws, body.number, body.synopsis, body.aspect_ratio, body.script, body.previs_skipped)

    @app.get("/api/films/{film_id}/journey")
    def film_journey(film_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return s.journey.state(film_id, ws)

    @app.put("/api/films/{film_id}/cast")
    def film_cast(film_id: str, body: CastSetIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.journey.set_cast(film_id, body.character_ids, body.location_ids, ws, body.release)

    @app.post("/api/films/{film_id}/script/draft")
    def film_script_draft(film_id: str, body: TextJobIn, ws: WS, s: Studio = Depends(get_studio)):
        """AI menulis naskah; hasilnya draf (belum disimpan)."""
        return s.journey.script_draft(film_id, ws, body.confirmed_cost, body.accept_unknown_cost, body.model)

    @app.post("/api/films/{film_id}/script/revise")
    def film_script_revise(film_id: str, body: ReviseIn, ws: WS, s: Studio = Depends(get_studio)):
        """AI mengubah naskah sesuai instruksi; hasilnya draf berformat Seedance + perbandingan per adegan (belum disimpan)."""
        return s.journey.script_revise(film_id, body.instruction, ws, body.confirmed_cost, body.accept_unknown_cost, body.model)

    @app.post("/api/films/{film_id}/split")
    def film_split(film_id: str, body: TextJobIn, ws: WS, s: Studio = Depends(get_studio)):
        """AI memecah naskah jadi adegan; hasilnya draf (belum disimpan)."""
        return s.journey.split_draft(film_id, ws, body.confirmed_cost, body.accept_unknown_cost, body.model)

    @app.post("/api/films/{film_id}/split/format")
    def film_split_format(film_id: str, ws: WS, s: Studio = Depends(get_studio)):
        """Draf adegan + beat dari naskah berformat Seedance; gratis (tanpa AI)."""
        return s.journey.split_format(film_id, ws)

    @app.post("/api/films/{film_id}/split/apply")
    def film_split_apply(film_id: str, body: SplitApplyIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.journey.apply_split(film_id, body.scenes, body.mode, ws)

    @app.delete("/api/films/{film_id}")
    def delete_film(film_id: str, ws: WS, s: Studio = Depends(get_studio)):
        s.films.delete(film_id, ws)
        return {"ok": True}

    @app.post("/api/films/{film_id}/render", status_code=202)
    def render_film(film_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return s.films.render(film_id, ws)

    # ---------- adegan, latar, tampilan (plan 08) ----------
    @app.post("/api/films/{film_id}/scenes")
    def add_scene(film_id: str, body: SceneAddIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.scenes.add(film_id, ws, body.after_scene_id, body.inherit, body.clip_id)

    @app.put("/api/films/{film_id}/scene-order")
    def reorder_scenes(film_id: str, body: SceneOrderIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.scenes.reorder(film_id, body.scene_ids, ws)

    @app.put("/api/scenes/{scene_id}")
    def update_scene(scene_id: str, body: SceneUpdateIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.scenes.update(scene_id, body.model_dump(exclude_unset=True), ws)

    @app.post("/api/films/{film_id}/scenes/bulk-delete")
    def bulk_delete_scenes(film_id: str, body: SceneIdsIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.scenes.delete_many(film_id, body.scene_ids, ws)

    @app.delete("/api/scenes/{scene_id}")
    def delete_scene(scene_id: str, ws: WS, s: Studio = Depends(get_studio)):
        s.scenes.delete(scene_id, ws)
        return {"ok": True}

    @app.post("/api/scenes/{scene_id}/keyframe")
    def scene_keyframe(scene_id: str, body: SceneKeyframeIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.scenes.keyframe(scene_id, body.model, ws, body.confirmed_cost, body.accept_unknown_cost)

    # ---------- beat adegan (plan 18) ----------
    @app.get("/api/scenes/{scene_id}/beats")
    def scene_beats(scene_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return s.beats.list(scene_id, ws)

    @app.put("/api/scenes/{scene_id}/beats")
    def put_scene_beats(scene_id: str, body: BeatsIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.beats.replace(scene_id, body.beats, body.note, ws)

    @app.post("/api/scenes/{scene_id}/beats/ai")
    def ai_scene_beats(scene_id: str, body: TextJobIn, ws: WS, s: Studio = Depends(get_studio)):
        """AI membuat shot sesuai format Seedance 2.0; hasilnya draf (belum disimpan)."""
        return s.beats.generate_ai(scene_id, ws, body.confirmed_cost, body.accept_unknown_cost, body.model)

    @app.get("/api/scenes/{scene_id}/prompt")
    def get_scene_prompt(scene_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return s.sprompt.get(scene_id, ws)

    @app.post("/api/scenes/{scene_id}/prompt/revise")
    def revise_scene_prompt(scene_id: str, body: ReviseIn, ws: WS, s: Studio = Depends(get_studio)):
        """AI mengubah prompt adegan sesuai instruksi; hasilnya draf yang sudah divalidasi (belum disimpan)."""
        return s.sprompt.revise(scene_id, body.instruction, ws, body.confirmed_cost, body.accept_unknown_cost, body.model)

    @app.post("/api/scenes/{scene_id}/prompt/check")
    def check_scene_prompt(scene_id: str, body: ScenePromptIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.sprompt.check(scene_id, body.prompt, ws)

    @app.put("/api/scenes/{scene_id}/prompt")
    def put_scene_prompt(scene_id: str, body: ScenePromptIn, ws: WS, s: Studio = Depends(get_studio)):
        """Simpan prompt adegan; latar, pemeran, beat, mood, dan durasi diturunkan darinya."""
        return s.sprompt.put(scene_id, body.prompt, ws)

    @app.post("/api/scenes/{scene_id}/revise")
    def revise_scene(scene_id: str, body: ReviseIn, ws: WS, s: Studio = Depends(get_studio)):
        """AI mengubah beat + catatan adegan sesuai instruksi; hasilnya draf (belum disimpan)."""
        return s.beats.revise_ai(scene_id, body.instruction, ws, body.confirmed_cost, body.accept_unknown_cost, body.model)

    @app.get("/api/scenes/{scene_id}/beats/versions")
    def scene_beat_versions(scene_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return s.beats.versions(scene_id, ws)

    @app.get("/api/scenes/{scene_id}/storyboard-video/preview")
    def storyboard_video_preview(scene_id: str, ws: WS, use_previs: bool = False, s: Studio = Depends(get_studio)):
        return s.sbvideo.preview(scene_id, ws, use_previs)

    @app.post("/api/scenes/{scene_id}/storyboard-video")
    def storyboard_video(scene_id: str, body: StoryboardVideoIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.sbvideo.generate(scene_id, ws, prompt=body.prompt, use_previs=body.use_previs, confirmed_cost=body.confirmed_cost,
                                  accept_unknown_cost=body.accept_unknown_cost, idempotency_key=body.idempotency_key)

    @app.post("/api/scenes/{scene_id}/beats/restore")
    def restore_scene_beats(scene_id: str, body: RestoreBeatsIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.beats.restore(scene_id, body.version_id, ws)

    # ---------- suara karakter (plan 18) ----------
    @app.get("/api/characters/{character_id}/voices")
    def character_voices(character_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return s.voices.list(character_id, ws)

    @app.post("/api/characters/{character_id}/voices")
    async def add_character_voice(character_id: str, ws: WS, description: str = Form(""), consent: bool = Form(False),
                                  note: str = Form(""), file: UploadFile | None = File(None), s: Studio = Depends(get_studio)):
        tmp = None
        try:
            if file is not None and file.filename:
                tmp = s.storage.new_path(".upload")
                size = 0
                with open(tmp, "wb") as fh:
                    while chunk := await file.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_VOICE_UPLOAD:
                            raise ServiceError("file audio terlalu besar", 413)
                        fh.write(chunk)
            return s.voices.add(character_id, description, tmp, consent, note, ws)
        finally:
            if tmp:
                tmp.unlink(missing_ok=True)

    @app.post("/api/voices/{voice_id}/activate")
    def activate_voice(voice_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return s.voices.activate(voice_id, ws)

    @app.delete("/api/voices/{voice_id}")
    def delete_voice(voice_id: str, ws: WS, s: Studio = Depends(get_studio)):
        s.voices.delete(voice_id, ws)
        return {"ok": True}

    @app.get("/api/voices/{voice_id}/file")
    def voice_file(voice_id: str, s: Studio = Depends(get_studio)):
        return FileResponse(s.voices.file_path(voice_id), media_type="audio/mp4")

    @app.post("/api/scenes/{scene_id}/blockout")
    def scene_blockout(scene_id: str, body: TextJobIn, ws: WS, s: Studio = Depends(get_studio)):
        """AI menyusun blockout 3D; hasilnya draf (belum disimpan ke adegan)."""
        return s.scenes.generate_blockout(scene_id, ws, body.confirmed_cost, body.accept_unknown_cost, body.model)

    @app.post("/api/scenes/{scene_id}/blockout/resolve")
    def scene_blockout_resolve(scene_id: str, body: ResolveIn, ws: WS, s: Studio = Depends(get_studio)):
        """Susunan siap render (gratis): set latar + properti adegan dengan koordinat dihitung pemecah tata letak. `layout` kosong = yang tersimpan."""
        return s.scenes.blockout_resolve(scene_id, ws, body.layout)

    @app.post("/api/scenes/{scene_id}/previs-video")
    def scene_previs_video(scene_id: str, body: SceneVideoIn, ws: WS, s: Studio = Depends(get_studio)):
        """Video adegan dari previs 3D (Seedance reference): video previs + gambar pemeran/latar."""
        return s.scenes.previs_video(scene_id, body.model, ws, body.duration, body.resolution, body.aspect_ratio, body.generate_audio,
                                     body.idempotency_key, body.confirmed_cost, body.accept_unknown_cost)

    @app.post("/api/scenes/{scene_id}/previs")
    async def scene_previs(scene_id: str, ws: WS, file: UploadFile = File(...), s: Studio = Depends(get_studio)):
        s.scenes.get(scene_id, ws)   # 404 sebelum menerima berkas
        tmp = s.storage.new_path(".upload")
        size = 0
        try:
            with open(tmp, "wb") as fh:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > s.s.max_video_upload_bytes:
                        raise ServiceError("file video terlalu besar", 413)
                    fh.write(chunk)
            ref = s.motion.add_upload(tmp, ws)   # jalur unggahan referensi yang sama: ffmpeg menormalkan WebM/MP4
        finally:
            tmp.unlink(missing_ok=True)
        return s.scenes.attach_previs(scene_id, ref, ws)

    @app.post("/api/scenes/{scene_id}/video")
    def scene_video(scene_id: str, body: SceneVideoIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.scenes.video(scene_id, body.model, ws, body.duration, body.resolution, body.aspect_ratio, body.generate_audio,
                              body.idempotency_key, body.confirmed_cost, body.accept_unknown_cost)

    @app.post("/api/locations/{location_id}/image")
    def location_image(location_id: str, body: LocationImageIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.scenes.location_image(location_id, body.model, ws, body.confirmed_cost, body.accept_unknown_cost)

    @app.post("/api/scenes/{scene_id}/duplicate")
    def duplicate_scene(scene_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return s.scenes.duplicate(scene_id, ws)

    @app.get("/api/locations")
    def list_locations(ws: WS, s: Studio = Depends(get_studio)):
        return s.scenes.list_locations(ws)

    @app.post("/api/locations")
    def create_location(body: LocationIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.scenes.create_location(body.name, body.description, body.image_id, ws)

    @app.put("/api/locations/{location_id}")
    def update_location(location_id: str, body: LocationUpdateIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.scenes.update_location(location_id, body.model_dump(exclude_unset=True), ws)

    @app.delete("/api/locations/{location_id}")
    def delete_location(location_id: str, ws: WS, s: Studio = Depends(get_studio)):
        s.scenes.delete_location(location_id, ws)
        return {"ok": True}

    @app.get("/api/characters/{character_id}/outfits")
    def list_outfits(character_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return s.scenes.list_outfits(character_id, ws)

    @app.post("/api/characters/{character_id}/outfits")
    def create_outfit(character_id: str, body: OutfitIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.scenes.create_outfit(character_id, body.name, body.description, body.image_id, ws)

    @app.put("/api/outfits/{outfit_id}")
    def update_outfit(outfit_id: str, body: LocationUpdateIn, ws: WS, s: Studio = Depends(get_studio)):
        return s.scenes.update_outfit(outfit_id, body.model_dump(exclude_unset=True), ws)

    @app.delete("/api/outfits/{outfit_id}")
    def delete_outfit(outfit_id: str, ws: WS, s: Studio = Depends(get_studio)):
        s.scenes.delete_outfit(outfit_id, ws)
        return {"ok": True}

    @app.get("/api/films/{film_id}/file")
    def film_file(film_id: str, s: Studio = Depends(get_studio)):
        return FileResponse(s.films.file_path(film_id), media_type="video/mp4")

    # ---------- workspace (plan 07) ----------
    @app.get("/api/workspaces")
    def list_workspaces(archived: bool = False, s: Studio = Depends(get_studio)):
        return s.workspaces.list_all(archived)

    @app.post("/api/workspaces")
    def create_workspace(body: WorkspaceIn, s: Studio = Depends(get_studio)):
        return s.workspaces.create(body.name)

    @app.put("/api/workspaces/{ws_id}")
    def rename_workspace(ws_id: str, body: WorkspaceIn, s: Studio = Depends(get_studio)):
        return s.workspaces.rename(ws_id, body.name)

    @app.get("/api/workspaces/{ws_id}/settings")
    def workspace_settings(ws_id: str, s: Studio = Depends(get_studio)):
        return s.workspaces.settings(ws_id)

    @app.put("/api/workspaces/{ws_id}/settings")
    def update_workspace_settings(ws_id: str, body: SettingsIn, s: Studio = Depends(get_studio)):
        patch = body.model_dump(exclude={"confirm_sync"}, exclude_unset=True)
        return s.workspaces.update_settings(ws_id, patch, body.confirm_sync)

    @app.post("/api/workspaces/{ws_id}/archive")
    def archive_workspace(ws_id: str, ws: WS, s: Studio = Depends(get_studio)):
        return s.workspaces.archive(ws_id, ws)

    @app.post("/api/workspaces/{ws_id}/restore")
    def restore_workspace(ws_id: str, s: Studio = Depends(get_studio)):
        return s.workspaces.restore(ws_id)

    @app.delete("/api/workspaces/{ws_id}")
    def delete_workspace(ws_id: str, ws: WS, s: Studio = Depends(get_studio)):
        """Hapus permanen workspace yang sudah diarsip; ws (header) = workspace aktif yang tidak boleh dihapus."""
        return s.workspaces.delete(ws_id, ws)

    @app.post("/api/workspaces/{target_id}/copy")
    def copy_to_workspace(target_id: str, body: CopyIn, ws: WS, s: Studio = Depends(get_studio)):
        """Salin gambar/karakter dari workspace aktif (header) ke workspace tujuan."""
        return s.workspaces.copy(ws, target_id, body.image_ids, body.character_ids)

    @app.get("/api/jobs")
    def list_jobs(s: Studio = Depends(get_studio)):
        """Job aktif + terbaru dari semua workspace, untuk dock antrian (tidak dicakup workspace)."""
        return [public_clip(c) for c in s.workspaces.jobs()]

    dist = Path(os.getenv("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


def app_factory() -> FastAPI:
    return create_app()
