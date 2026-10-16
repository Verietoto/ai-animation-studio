"""Server OpenRouter palsu untuk pengembangan/uji UI tanpa API key dan tanpa biaya.

Jalankan:  uvicorn scripts.fake_openrouter:app --port 9000
Lalu       OPENROUTER_API_KEY=fake OPENROUTER_BASE_URL=http://127.0.0.1:9000/api/v1 ...
Bentuk respons mengikuti asumsi di backend/app/openrouter.py (belum diverifikasi ke API nyata).
"""
import base64
import io
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, Response
from PIL import Image

app = FastAPI()
_tmp = Path(tempfile.mkdtemp())
_calls: dict[str, int] = {}


def _video() -> bytes:
    out = _tmp / "v.mp4"
    if not out.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=320x180:d=2:r=24",
                        "-f", "lavfi", "-i", "sine=frequency=330:d=2", "-pix_fmt", "yuv420p", str(out)], check=True)
    return out.read_bytes()


@app.get("/api/v1/videos/models")
def models():
    return {"data": [{"id": "fake/seedance", "name": "Fake Seedance", "supported_durations": [4, 8],
                      "supported_resolutions": ["720p", "1080p"], "supported_aspect_ratios": ["16:9", "9:16"],
                      "supported_frame_images": ["first_frame", "last_frame"]}]}


@app.post("/api/v1/videos")
def submit():
    n = len(_calls) + 1
    _calls[f"job{n}"] = 0
    return {"id": f"job{n}", "status": "pending"}


@app.get("/api/v1/videos/{job}/content")
def content(job: str):
    return Response(_video(), media_type="video/mp4")


@app.get("/api/v1/videos/{job}")
def status(job: str):
    _calls[job] = _calls.get(job, 0) + 1
    return {"id": job, "status": "completed" if _calls[job] >= 2 else "in_progress", "usage": {"cost": 0.12}}


@app.get("/api/v1/models")
def image_models():
    return {"data": [{"id": "openai/gpt-image-2", "architecture": {"input_modalities": ["text", "image"]}}]}


@app.post("/api/v1/chat/completions")
def chat():
    buf = io.BytesIO()
    Image.linear_gradient("L").convert("RGB").resize((320, 240)).save(buf, "PNG")
    url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return {"choices": [{"message": {"content": "ok", "images": [{"type": "image_url", "image_url": {"url": url}}]}}],
            "usage": {"cost": 0.006}}
