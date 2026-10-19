import base64
import io
import json
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.openrouter import OpenRouterClient

VIDEO_MODEL = {"id": "bytedance/seedance-2.5", "supported_durations": [4, 8],
               "pricing_skus": {"duration_seconds": "0.05"},
               "supported_resolutions": ["720p"], "supported_aspect_ratios": ["16:9"],
               "supported_frame_images": ["first_frame", "last_frame"], "generate_audio": True}
NO_AUDIO_MODEL = {"id": "x/no-audio", "supported_durations": [4], "supported_frame_images": ["first_frame"],
                  "generate_audio": False, "pricing_skus": {"duration_seconds": "0.1"}}
UNPRICED_MODEL = {"id": "x/unpriced", "supported_durations": None, "supported_frame_images": ["first_frame"],
                  "generate_audio": None, "pricing_skus": {}}
EDIT_ONLY_MODEL = {"id": "x/video-edit", "supported_durations": None, "supported_frame_images": None,
                   "generate_audio": False}


def png_bytes(color=(200, 50, 50), size=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def make_video(path: Path, color="red", seconds=1, audio=True) -> Path:
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=160x90:d={seconds}:r=24"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:d={seconds}"]
    cmd += ["-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True)
    return path


class FakeOpenRouter:
    """Meniru API OpenRouter berdasarkan dokumentasi; menyimpan permintaan untuk diperiksa."""

    def __init__(self, tmp: Path):
        self.requests: list[httpx.Request] = []
        self.video_status = "completed"
        self.video_bytes = make_video(tmp / "remote.mp4", color="blue").read_bytes()
        self.edit_returns_image = True
        self.submit_count = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/videos/models"):
            return httpx.Response(200, json={"data": [VIDEO_MODEL, NO_AUDIO_MODEL, EDIT_ONLY_MODEL, UNPRICED_MODEL]})
        if path.endswith("/videos") and request.method == "POST":
            self.submit_count += 1
            return httpx.Response(200, json={"id": f"job{self.submit_count}", "status": "pending"})
        if path.endswith("/content"):
            return httpx.Response(200, content=self.video_bytes)
        if "/videos/" in path:
            return httpx.Response(200, json={"id": path.split("/")[-1], "status": self.video_status,
                                             "usage": {"cost": 0.4}})
        if path.endswith("/images") and request.method == "POST":
            if not self.edit_returns_image:
                return httpx.Response(200, json={"data": [], "usage": {"cost": 0}})
            b64 = base64.b64encode(png_bytes((10, 200, 10))).decode()
            return httpx.Response(200, json={"created": 1, "data": [{"b64_json": b64, "media_type": "image/png"}],
                                             "usage": {"cost": 0.01}})
        if "/images/models/" in path and path.endswith("/endpoints"):
            return httpx.Response(200, json={"id": "m", "endpoints": [{"provider_name": "P", "pricing": [
                {"billable": "output_image", "unit": "image", "cost_usd": 0.02}, {"billable": "input_image", "unit": "image", "cost_usd": 0}]}]})
        if path.endswith("/images/models"):
            return httpx.Response(200, json={"data": [
                {"id": "openai/gpt-image-2", "architecture": {"input_modalities": ["text", "image"]},
                 "supported_parameters": {
                     "aspect_ratio": {"type": "enum", "values": ["1:1", "16:9", "auto"]},
                     "quality": {"type": "enum", "values": ["auto", "low", "high"]},
                     "input_references": {"type": "range", "min": 0, "max": 3}}},
                {"id": "x/text-only", "architecture": {"input_modalities": ["text"]}}]})
        return httpx.Response(404, json={"error": "unknown"})

    def last_json(self, suffix: str) -> dict:
        req = [r for r in self.requests if r.url.path.endswith(suffix) and r.method == "POST"][-1]
        return json.loads(req.content)


@pytest.fixture
def fake(tmp_path):
    return FakeOpenRouter(tmp_path)


@pytest.fixture
def settings(tmp_path):
    return Settings(api_key="sk-test-1234567890", base_url="https://or.test/api/v1",
                    data_dir=tmp_path / "data", daily_budget_usd=5.0, poll_interval=999,
                    job_timeout=1800, max_upload_bytes=1024 * 1024, max_chain=2)


class ConfirmingClient:
    """Meniru UI: untuk tiap endpoint generate, minta estimasi lalu kirim `confirmed_cost`.
    Tes yang menguji konfirmasi memakai `api.raw` (tanpa konfirmasi otomatis)."""

    GENERATE = ("/api/clips", "/extend", "/edit")

    def __init__(self, tc):
        self.raw = tc
        self.studio = None

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def post(self, url, json=None, **kw):
        if json is not None and any(url.endswith(g) or url == g for g in self.GENERATE) and "confirmed_cost" not in json:
            model = json["model"]
            kind = "image_edit" if url.endswith("/edit") else "video"
            body = {"kind": kind, "model": model, **{k: json[k] for k in ("duration", "resolution", "aspect_ratio", "generate_audio", "quality") if k in json}}
            body["reference_count"] = len(json.get("reference_image_ids", []))
            est = self.raw.post("/api/estimate", json=body)
            if est.status_code == 200:
                data = est.json()
                json = {**json, "confirmed_cost": data["high"], "accept_unknown_cost": data["confidence"] == "unknown"}
        return self.raw.post(url, json=json, **kw)


@pytest.fixture
def api(settings, fake):
    client = OpenRouterClient(settings.api_key, settings.base_url, transport=httpx.MockTransport(fake))
    app = create_app(settings, client)
    with TestClient(app) as tc:
        wrapped = ConfirmingClient(tc)
        wrapped.studio = app.state.studio
        yield wrapped


def upload(api) -> dict:
    r = api.post("/api/images", files={"file": ("a.png", png_bytes(), "image/png")})
    assert r.status_code == 200, r.text
    return r.json()
