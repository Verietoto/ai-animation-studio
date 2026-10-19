"""Uji nyata (BERBIAYA kecil) untuk memverifikasi asumsi kontrak OpenRouter.

Butuh OPENROUTER_API_KEY. Hanya membaca daftar model secara default (gratis).
Tambahkan --edit untuk satu edit gambar murah. Tambahkan --video MODEL untuk satu job video (berbayar).
"""
import argparse
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from PIL import Image  # noqa: E402

from app import media  # noqa: E402
from app.openrouter import OpenRouterClient  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--edit", metavar="MODEL", help="mis. openai/gpt-image-2")
p.add_argument("--video", metavar="MODEL", help="job video berbayar")
a = p.parse_args()
c = OpenRouterClient(os.environ["OPENROUTER_API_KEY"], os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))

models = c.list_video_models()
print(f"{len(models)} model video. Contoh field model pertama:")
print(json.dumps(models[0], indent=2)[:1500])
print(f"{len(c.list_image_models())} model gambar yang menerima input gambar")

buf = io.BytesIO(); Image.new("RGB", (512, 512), (90, 140, 200)).save(buf, "PNG")
url = media.to_data_url(buf.getvalue())
if a.edit:
    r = c.edit_image(a.edit, "tambahkan matahari kuning di pojok", [url], quality="low")
    print("edit: images =", len(r.get("data") or []), "| usage =", r.get("usage"))
if a.video:
    r = c.submit_video({"model": a.video, "prompt": "kamera zoom pelan", "generate_audio": False,
                        "frame_images": [{"type": "image_url", "image_url": {"url": url}, "frame_type": "first_frame"}]})
    print("submit:", r)
    while True:
        j = c.get_video_job(r["id"]); print("status:", j.get("status"), j.get("usage"))
        if str(j.get("status")).lower() in {"completed", "failed"}: break
        time.sleep(10)
    if j.get("status") == "completed":
        print("bytes:", len(c.download_video(r["id"])))
