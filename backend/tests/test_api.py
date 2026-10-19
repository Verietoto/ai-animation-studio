import subprocess
from pathlib import Path

from conftest import make_video, png_bytes, upload

VIDEO = {"model": "bytedance/seedance-2.5", "prompt": "kamera zoom pelan", "duration": 4,
         "resolution": "720p", "aspect_ratio": "16:9"}


def complete(api, clip_id):
    api.studio.poll_once()
    return api.get(f"/api/clips/{clip_id}").json()


def test_upload_rejects_non_image(api):
    r = api.post("/api/images", files={"file": ("a.png", b"bukan gambar", "image/png")})
    assert r.status_code == 415


def test_upload_rejects_oversize(api):
    r = api.post("/api/images", files={"file": ("a.png", b"x" * (1024 * 1024 + 10), "image/png")})
    assert r.status_code == 413


def test_upload_normalizes_large_rgba(api):
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGBA", (4000, 1000), (0, 0, 0, 0)).save(buf, "PNG")
    r = api.post("/api/images", files={"file": ("a.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200
    assert max(r.json()["width"], r.json()["height"]) == 2048


def test_image_to_video_flow(api, fake):
    img = upload(api)
    r = api.post("/api/clips", json={**VIDEO, "image_id": img["id"]})
    assert r.status_code == 200, r.text
    clip = r.json()
    assert clip["status"] == "submitted"
    sent = fake.last_json("/videos")
    assert sent["frame_images"][0]["frame_type"] == "first_frame"
    assert sent["frame_images"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    done = complete(api, clip["id"])
    assert done["status"] == "completed" and done["cost"] == 0.4 and done["has_file"]
    assert api.get(f"/api/clips/{clip['id']}/file").status_code == 200
    assert "path" not in done  # path internal tidak bocor


def test_api_key_sent_only_as_bearer_never_in_responses(api, fake):
    img = upload(api)
    clip = api.post("/api/clips", json={**VIDEO, "image_id": img["id"]}).json()
    assert "sk-test" not in str(clip)
    assert all(r.headers["authorization"] == "Bearer sk-test-1234567890" for r in fake.requests)


def test_invalid_params_rejected_before_calling_provider(api, fake):
    img = upload(api)
    r = api.post("/api/clips", json={**VIDEO, "image_id": img["id"], "duration": 99})
    assert r.status_code == 400 and "duration" in r.json()["detail"]
    assert fake.submit_count == 0
    r = api.post("/api/clips", json={**VIDEO, "image_id": img["id"], "model": "nope/nope"})
    assert r.status_code == 400


def test_idempotency_key_prevents_duplicate_job(api, fake):
    img = upload(api)
    body = {**VIDEO, "image_id": img["id"], "idempotency_key": "abc"}
    a = api.post("/api/clips", json=body).json()
    b = api.post("/api/clips", json=body).json()
    assert a["id"] == b["id"] and fake.submit_count == 1


def test_failed_job_keeps_error(api, fake):
    img = upload(api)
    clip = api.post("/api/clips", json={**VIDEO, "image_id": img["id"]}).json()
    fake.video_status = "failed"
    assert complete(api, clip["id"])["status"] == "failed"


def test_job_timeout(api, fake, settings):
    img = upload(api)
    clip = api.post("/api/clips", json={**VIDEO, "image_id": img["id"]}).json()
    fake.video_status = "in_progress"
    api.studio.s = type(settings)(**{**settings.__dict__, "job_timeout": -1})
    assert complete(api, clip["id"])["status"] == "failed"


def test_download_failure_then_retry(api, fake):
    img = upload(api)
    clip = api.post("/api/clips", json={**VIDEO, "image_id": img["id"]}).json()
    good = fake.video_bytes
    fake.video_bytes = b"bukan video"
    assert complete(api, clip["id"])["status"] == "failed_download"
    fake.video_bytes = good
    r = api.post(f"/api/clips/{clip['id']}/retry-download")
    assert r.json()["status"] == "completed"


def test_jobs_resume_after_restart(settings, fake, api):
    """Job aktif di DB dilanjutkan oleh instance baru (simulasi restart)."""
    import httpx
    from app.main import create_app
    from app.openrouter import OpenRouterClient
    from fastapi.testclient import TestClient
    img = upload(api)
    clip = api.post("/api/clips", json={**VIDEO, "image_id": img["id"]}).json()
    client = OpenRouterClient(settings.api_key, settings.base_url, transport=httpx.MockTransport(fake))
    with TestClient(create_app(settings, client)) as api2:
        api2.app.state.studio.poll_once()
        assert api2.get(f"/api/clips/{clip['id']}").json()["status"] == "completed"


def test_daily_budget_blocks_new_jobs(api, fake):
    img = upload(api)
    clip = api.post("/api/clips", json={**VIDEO, "image_id": img["id"]}).json()
    complete(api, clip["id"])  # biaya 0.4
    api.studio.s = type(api.studio.s)(**{**api.studio.s.__dict__, "daily_budget_usd": 0.1})
    r = api.post("/api/clips", json={**VIDEO, "image_id": img["id"]})
    assert r.status_code == 402


def test_extend_uses_last_frame_and_chain_limit(api, fake):
    img = upload(api)
    c1 = api.post("/api/clips", json={**VIDEO, "image_id": img["id"]}).json()
    assert api.post(f"/api/clips/{c1['id']}/extend", json={"prompt": "lanjut", "model": VIDEO["model"]}).status_code == 409  # belum selesai
    complete(api, c1["id"])
    r = api.post(f"/api/clips/{c1['id']}/extend", json={"prompt": "lanjut", "model": VIDEO["model"], "duration": 4})
    assert r.status_code == 200, r.text
    c2 = r.json()
    assert c2["parent_clip_id"] == c1["id"] and c2["chain_depth"] == 1
    frames = [i for i in api.get("/api/images").json() if i["kind"] == "frame"]
    assert len(frames) == 1 and c2["source_image_id"] == frames[0]["id"]
    complete(api, c2["id"])
    c3 = api.post(f"/api/clips/{c2['id']}/extend", json={"prompt": "lagi", "model": VIDEO["model"]}).json()
    complete(api, c3["id"])
    r = api.post(f"/api/clips/{c3['id']}/extend", json={"prompt": "lagi", "model": VIDEO["model"]})
    assert r.status_code == 400 and "maksimum" in r.json()["detail"]


def test_merge_chain_produces_playable_video(api, fake):
    img = upload(api)
    c1 = api.post("/api/clips", json={**VIDEO, "image_id": img["id"]}).json()
    complete(api, c1["id"])
    c2 = api.post(f"/api/clips/{c1['id']}/extend", json={"prompt": "lanjut", "model": VIDEO["model"]}).json()
    complete(api, c2["id"])
    r = api.post(f"/api/clips/{c2['id']}/merge")
    assert r.status_code == 200 and r.json()["has_merged"]
    data = api.get(f"/api/clips/{c2['id']}/merged").content
    assert len(data) > 1000


def test_edit_image(api, fake):
    img = upload(api)
    r = api.post(f"/api/images/{img['id']}/edit", json={"prompt": "ubah latar jadi hutan", "model": "openai/gpt-image-2"})
    assert r.status_code == 200, r.text
    edited = r.json()[0]
    assert edited["kind"] == "edit" and edited["parent_image_id"] == img["id"] and edited["cost"] == 0.01
    body = fake.last_json("/chat/completions")
    assert body["modalities"] == ["image", "text"]
    assert body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png")
    # hasil edit bisa langsung jadi video
    assert api.post("/api/clips", json={**VIDEO, "image_id": edited["id"]}).status_code == 200


def test_edit_text_only_reply_is_error_not_new_version(api, fake):
    img = upload(api)
    fake.edit_returns_image = False
    r = api.post(f"/api/images/{img['id']}/edit", json={"prompt": "x", "model": "openai/gpt-image-2"})
    assert r.status_code == 422 and "Maaf" in r.json()["detail"]
    assert len(api.get("/api/images").json()) == 1


def test_image_models_filters_text_only(api):
    ids = [m["id"] for m in api.get("/api/models/image").json()]
    assert ids == ["openai/gpt-image-2"]


def test_missing_api_key_gives_clear_error(settings, fake):
    import httpx
    from app.main import create_app
    from app.openrouter import OpenRouterClient
    from fastapi.testclient import TestClient
    s = type(settings)(**{**settings.__dict__, "api_key": None})
    client = OpenRouterClient(None, s.base_url, transport=httpx.MockTransport(fake))
    with TestClient(create_app(s, client)) as api:
        r = api.get("/api/models/video")
        assert r.status_code == 502 and "OPENROUTER_API_KEY" in r.json()["detail"]


def test_error_text_redacts_token(api, fake):
    from app.openrouter import _clean
    assert "sk-" not in _clean("bad key sk-or-v1-abcdef1234567890 rejected")


def test_extract_last_frame_skips_black_frames(tmp_path):
    from app import media
    video = tmp_path / "fade.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=160x90:d=2:r=24",
                    "-vf", "fade=t=out:st=1:d=1", "-pix_fmt", "yuv420p", str(video)], check=True)
    out = tmp_path / "f.png"
    media.extract_last_frame(video, out)
    assert out.exists()


def test_merge_handles_clip_without_audio(tmp_path):
    from app import media
    a = make_video(tmp_path / "a.mp4", "red", audio=True)
    b = make_video(tmp_path / "b.mp4", "green", audio=False)
    out = tmp_path / "m.mp4"
    media.merge_videos([a, b], out)
    info = media.probe(out)
    assert info["has_audio"] and info["duration"] > 1.8


def test_audio_rejected_for_model_without_audio(api, fake):
    img = upload(api)
    r = api.post("/api/clips", json={"image_id": img["id"], "prompt": "x", "model": "x/no-audio", "generate_audio": True})
    assert r.status_code == 400 and "suara" in r.json()["detail"]
    ok = api.post("/api/clips", json={"image_id": img["id"], "prompt": "x", "model": "x/no-audio", "generate_audio": False})
    assert ok.status_code == 200
    assert fake.submit_count == 1


def test_non_image_to_video_model_rejected(api, fake):
    img = upload(api)
    r = api.post("/api/clips", json={"image_id": img["id"], "prompt": "x", "model": "x/video-edit"})
    assert r.status_code == 400 and fake.submit_count == 0
