import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import media
from .config import Settings
from .db import Database
from .openrouter import OpenRouterClient
from .service import ServiceError, Studio
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


class ExtendIn(Confirm):
    prompt: str = Field(max_length=4000)
    model: str
    duration: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    generate_audio: bool = False
    idempotency_key: str | None = Field(default=None, max_length=100)


class EstimateIn(BaseModel):
    kind: str = Field(pattern="^(video|image_edit|character_sheet)$")
    model: str
    duration: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    generate_audio: bool = False
    reference_count: int = Field(default=0, ge=0, le=20)   # gambar referensi tambahan (edit foto)
    quality: str | None = None


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


def create_app(settings: Settings | None = None, client: OpenRouterClient | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.data_dir / "studio.db")
    storage = Storage(settings.data_dir / "media")
    client = client or OpenRouterClient(settings.api_key, settings.base_url)
    studio = Studio(settings, db, storage, client)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        studio.start()
        yield
        studio.stop()

    app = FastAPI(title="AI Animation Studio", lifespan=lifespan)
    app.state.studio = studio

    @app.exception_handler(ServiceError)
    async def service_error(_: Request, exc: ServiceError):
        return JSONResponse({"detail": str(exc), **exc.extra}, status_code=exc.status)

    def get_studio() -> Studio:
        return studio

    def public_clip(c: dict) -> dict:
        return {k: v for k, v in c.items() if k not in ("path", "merged_path")} | {
            "has_file": bool(c["path"]), "has_merged": bool(c["merged_path"])}

    def public_image(i: dict) -> dict:
        return {k: v for k, v in i.items() if k != "path"}

    @app.get("/api/health")
    def health():
        return {"ffmpeg": media.ffmpeg_available(), "api_key": bool(settings.api_key),
                "spent_today": studio.db.spent_today(), "daily_budget": settings.daily_budget_usd,
                "max_per_job": settings.max_cost_per_job}

    @app.post("/api/estimate")
    def estimate(body: EstimateIn, s: Studio = Depends(get_studio)):
        """Perkiraan biaya tanpa efek samping; parameter divalidasi seperti saat generate."""
        if body.kind == "character_sheet":
            est = s.estimate_sheet(body.model, len(s.SHEET_VIEWS), body.aspect_ratio, body.quality)
        elif body.kind == "video":
            params = {k: v for k, v in {"duration": body.duration, "resolution": body.resolution,
                                        "aspect_ratio": body.aspect_ratio}.items() if v is not None}
            params["generate_audio"] = body.generate_audio
            s._validate_video_params(body.model, params)
            est = s.estimate_video_job(body.model, params)
        else:
            options = {k: v for k, v in {"resolution": body.resolution, "aspect_ratio": body.aspect_ratio,
                                         "quality": body.quality}.items() if v}
            s._validate_image_params(body.model, options, 1 + body.reference_count)
            est = s.estimate_image_job(body.model, n_inputs=1 + body.reference_count, resolution=body.resolution)
        state = s.budget_state()
        blocked = None
        if est.confidence != "unknown" and est.high > state["max_per_job"]:
            blocked = f"melebihi batas per job ${state['max_per_job']:.2f}"
        elif state["committed_today"] + est.high > state["daily_budget"]:
            blocked = "melebihi batas harian"
        return {**est.as_dict(), **state, "blocked": blocked}

    @app.get("/api/models/video")
    def video_models(s: Studio = Depends(get_studio)):
        return s.video_models()

    @app.get("/api/models/image")
    def image_models(s: Studio = Depends(get_studio)):
        return s.image_models()

    @app.post("/api/images")
    async def upload_image(file: UploadFile = File(...), s: Studio = Depends(get_studio)):
        data = await file.read(s.s.max_upload_bytes + 1)
        return public_image(s.add_upload(data))

    @app.get("/api/images")
    def list_images(s: Studio = Depends(get_studio)):
        return [public_image(i) for i in s.db.all("SELECT * FROM images ORDER BY created_at DESC LIMIT 200")]

    @app.get("/api/images/{image_id}/file")
    def image_file(image_id: str, s: Studio = Depends(get_studio)):
        return FileResponse(s.storage.resolve(s.get_image(image_id)["path"]), media_type="image/png")

    @app.post("/api/images/{image_id}/edit")
    def edit_image(image_id: str, body: EditIn, s: Studio = Depends(get_studio)):
        return [public_image(i) for i in s.edit_image(
            image_id, body.prompt, body.model, body.reference_image_ids,
            resolution=body.resolution, aspect_ratio=body.aspect_ratio, quality=body.quality,
            confirmed_cost=body.confirmed_cost, accept_unknown_cost=body.accept_unknown_cost,
            character_id=body.character_id)]

    def public_character(c: dict) -> dict:
        return {**c, "images": s_images(c["id"])}

    def s_images(character_id: str) -> list[dict]:
        return studio.character_images(character_id)

    @app.post("/api/characters")
    def create_character(body: CharacterIn, s: Studio = Depends(get_studio)):
        return public_character(s.create_character(body.name, body.description, body.source_image_id))

    @app.get("/api/characters")
    def list_characters(s: Studio = Depends(get_studio)):
        return [public_character(c) for c in s.db.all("SELECT * FROM characters ORDER BY created_at DESC")]

    @app.get("/api/characters/{character_id}")
    def get_character(character_id: str, s: Studio = Depends(get_studio)):
        return public_character(s.get_character(character_id))

    @app.post("/api/characters/{character_id}/images")
    def add_character_image(character_id: str, body: AddImageIn, s: Studio = Depends(get_studio)):
        s.add_character_image(character_id, body.image_id, body.label)
        return public_character(s.get_character(character_id))

    @app.post("/api/characters/{character_id}/sheet")
    def character_sheet(character_id: str, body: SheetIn, s: Studio = Depends(get_studio)):
        s.generate_sheet(character_id, body.model, body.aspect_ratio, body.quality,
                         body.confirmed_cost, body.accept_unknown_cost)
        return public_character(s.get_character(character_id))

    @app.post("/api/clips")
    def create_clip(body: ClipIn, s: Studio = Depends(get_studio)):
        return public_clip(s.create_clip(**body.model_dump()))

    @app.get("/api/clips")
    def list_clips(s: Studio = Depends(get_studio)):
        return [public_clip(c) for c in s.db.all("SELECT * FROM clips ORDER BY created_at DESC LIMIT 200")]

    @app.get("/api/clips/{clip_id}")
    def get_clip(clip_id: str, s: Studio = Depends(get_studio)):
        return public_clip(s.get_clip(clip_id))

    @app.get("/api/clips/{clip_id}/file")
    def clip_file(clip_id: str, s: Studio = Depends(get_studio)):
        clip = s.get_clip(clip_id)
        if not clip["path"]:
            raise HTTPException(404, "file belum tersedia")
        return FileResponse(s.storage.resolve(clip["path"]), media_type="video/mp4")

    @app.post("/api/clips/{clip_id}/extend")
    def extend_clip(clip_id: str, body: ExtendIn, s: Studio = Depends(get_studio)):
        return public_clip(s.extend_clip(clip_id, **body.model_dump()))

    @app.post("/api/clips/{clip_id}/merge")
    def merge_clip(clip_id: str, s: Studio = Depends(get_studio)):
        return public_clip(s.merge_chain(clip_id))

    @app.get("/api/clips/{clip_id}/merged")
    def merged_file(clip_id: str, s: Studio = Depends(get_studio)):
        clip = s.get_clip(clip_id)
        if not clip["merged_path"]:
            raise HTTPException(404, "belum digabung")
        return FileResponse(s.storage.resolve(clip["merged_path"]), media_type="video/mp4")

    @app.post("/api/clips/{clip_id}/retry-download")
    def retry_download(clip_id: str, s: Studio = Depends(get_studio)):
        return public_clip(s.retry_download(clip_id))

    dist = Path(os.getenv("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


def app_factory() -> FastAPI:
    return create_app()
