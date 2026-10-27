"""Spike plan 10: satu job flux_edit memakai video UNGGAHAN lewat tunnel cloudflared. Batas keras $0,20.
Jalankan: set -a; . ./.env; set +a; PUBLIC_TUNNEL=cloudflared backend/../.venv/bin/python scripts/spike_tunnel.py
Memakai DATA_DIR sementara; tidak menyentuh database asli."""
import dataclasses, os, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app

CAP = 0.20
tmp = Path(tempfile.mkdtemp(prefix="spike10-"))
video = tmp / "ref.mp4"
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=854x480:d=3:r=24",
                "-f", "lavfi", "-i", "sine=frequency=440:d=3", "-pix_fmt", "yuv420p", "-shortest", str(video)], check=True)
st = dataclasses.replace(Settings.from_env(), data_dir=tmp / "data", poll_interval=999, max_cost_per_job=CAP)
assert st.api_key and st.public_tunnel == "cloudflared", "butuh OPENROUTER_API_KEY dan PUBLIC_TUNNEL=cloudflared"
with TestClient(create_app(st)) as tc:
    assert tc.get("/api/health").json()["public_media"] is True
    ref = tc.post("/api/references", files={"file": ("ref.mp4", video.read_bytes(), "video/mp4")}).json()
    print("referensi:", ref["id"][:8], ref["duration"], "dtk", ref["width"], "x", ref["height"])
    body = {"kind": "motion", "mode": "flux_edit", "model": "black-forest-labs/flux-video-edit", "reference_id": ref["id"]}
    est = tc.post("/api/estimate", json=body).json()
    print("estimasi: low %.4f high %.4f" % (est["low"], est["high"]))
    assert est["high"] <= CAP, "estimasi melebihi batas spike"
    t = time.time()
    r = tc.post("/api/motion", json={"mode": "flux_edit", "model": body["model"], "reference_id": ref["id"],
                "prompt": "Replace the test pattern with a calm ocean wave. Keep the camera and timing unchanged.",
                "confirmed_cost": est["high"]})
    print("submit:", r.status_code, r.text[:300] if r.status_code != 200 else "ok", "(%.1f dtk, termasuk tunnel naik)" % (time.time() - t))
    if r.status_code == 200:
        cid = r.json()["id"]
        studio = tc.app.state.studio
        for _ in range(90):
            studio.poll_once()
            c = tc.get(f"/api/clips/{cid}").json()
            if c["status"] in ("completed", "failed", "failed_download"):
                break
            time.sleep(5)
        print("hasil:", c["status"], "biaya", c["cost"], "error", c["error"])
