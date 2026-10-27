"""Spike plan 10 (pembanding): video SAMA dikirim ke FLUX Video Edit lewat (A) URL milik OpenRouter dan (B) tunnel cloudflared.
Batas keras $0,20 (dihitung dari biaya nyata langkah 1 + estimasi eksak langkah 2). Tidak memakai database aplikasi.
Jalankan: set -a; . ./.env; set +a; PYTHONUNBUFFERED=1 .venv/bin/python scripts/spike_tunnel_compare.py
"""
import os, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.openrouter import OpenRouterClient, OpenRouterError
from app.publicmedia import TunnelPublicMedia

CAP, FLUX_PER_SECOND, SECONDS = 0.20, 0.03, 2
PROMPT = "Change the main object into a red balloon. Keep the camera and timing unchanged."
c = OpenRouterClient(os.environ["OPENROUTER_API_KEY"], "https://openrouter.ai/api/v1")
tmp = Path(tempfile.mkdtemp(prefix="spike10b-"))


def wait(job_id, limit=900):
    t = time.time()
    while time.time() - t < limit:
        job = c.get_video_job(job_id)
        if str(job.get("status")).lower() in ("completed", "failed", "cancelled", "expired"):
            return job
        time.sleep(5)
    return c.get_video_job(job_id)


def summary(job):
    return {"status": job.get("status"), "cost": (job.get("usage") or {}).get("cost"), "error": str(job.get("error"))[:260]}


# langkah 1: video sumber 2 dtk di OpenRouter (juga memberi URL bertanda tangan milik OpenRouter)
gen = c.submit_video({"model": "x-ai/grok-imagine-video-1.5-lite", "prompt": "a small wooden toy on a table, steady camera, soft daylight",
                      "duration": SECONDS, "resolution": "480p", "aspect_ratio": "16:9", "generate_audio": False})
job = wait(gen["id"])
print("langkah 1 (buat video sumber):", summary(job), flush=True)
if str(job.get("status")).lower() != "completed":
    sys.exit("video sumber gagal; berhenti")
spent = (job.get("usage") or {}).get("cost") or 0.04
for _ in range(10):   # `urls` muncul beberapa detik setelah completed
    job = c.get_video_job(gen["id"])
    if job.get("urls"):
        break
    time.sleep(2)
signed = job["urls"][0]
src = tmp / "src.mp4"
src.write_bytes(c.download_video(gen["id"]))
print("sumber: %d byte, URL bertanda tangan OpenRouter: %s" % (src.stat().st_size, "ada" if signed else "tidak ada"), flush=True)

need = 2 * FLUX_PER_SECOND * SECONDS
if spent + need > CAP:
    sys.exit("proyeksi $%.3f melebihi batas $%.2f; berhenti" % (spent + need, CAP))

# langkah 2: dua job FLUX dengan berkas yang sama, hanya asal URL yang berbeda
media = TunnelPublicMedia(ttl=3600)
try:
    key, tunnel_url = media.publish(src)
    print("tunnel siap:", tunnel_url.split("/")[2], flush=True)
    ids = {}
    for label, url in (("A (URL OpenRouter)", signed), ("B (tunnel)", tunnel_url)):
        try:
            ids[label] = c.submit_video({"model": "black-forest-labs/flux-video-edit", "prompt": PROMPT,
                                         "input_references": [{"type": "video_url", "video_url": {"url": url}}]})["id"]
            print("kirim", label, "diterima", flush=True)
        except OpenRouterError as exc:
            print("kirim", label, "DITOLAK saat submit:", str(exc)[:260], flush=True)
    results = {label: wait(jid) for label, jid in ids.items()}   # tunnel harus tetap hidup sampai keduanya selesai
    for label, job in results.items():
        print("hasil", label, summary(job), flush=True)
finally:
    media.close()
