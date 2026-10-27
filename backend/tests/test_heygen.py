"""Plan 20: HeyGen Video 1 sebagai model video proyek (OpenRouter palsu, tanpa biaya nyata)."""
import json
import time

import pytest

from app import pricing
from test_project_settings import put, settings
from test_scenes import film, put as put_scene, scene
from test_storyboard_video import last_video_request
from test_workspaces import char, up

HEY = {"id": "heygen/heygen-video-1", "supported_durations": list(range(5, 16)), "supported_resolutions": ["480p", "768p", "2K"],
       "supported_aspect_ratios": ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16"], "supported_frame_images": ["first_frame"], "generate_audio": False,
       "pricing_skus": {"duration_seconds_2k": "0.1", "duration_seconds_480p": "0.02", "duration_seconds_768p": "0.036", "reference_input_images": "0.04",
                        "reference_duration_seconds_2k": "0.18", "reference_duration_seconds_480p": "0.07", "reference_duration_seconds_768p": "0.1"}}


def test_pricing_uses_reference_rate_and_per_image_fee_only_with_references():
    plain = pricing.estimate_video(HEY, duration=5, resolution="480p", audio=False, mode="ref", reference_images=0)
    refd = pricing.estimate_video(HEY, duration=5, resolution="480p", audio=False, mode="ref", reference_images=3)
    assert plain.high == pytest.approx(0.10) and refd.high == pytest.approx(5 * 0.07 + 3 * 0.04)      # 0.47
    assert pricing.estimate_video(HEY, duration=5, resolution="2K", audio=False, mode="ref", reference_images=1).high == pytest.approx(5 * 0.18 + 0.04)
    assert pricing.estimate_video(HEY, duration=5, resolution="480p", audio=False, mode="i2v", image_inputs=1).high == pytest.approx(0.10)   # frame awal: tarif biasa


@pytest.fixture
def hey(api):
    api.studio._models = (time.time(), [*api.studio.video_models(), HEY])
    return api


def test_settings_reject_unsupported_resolution_or_ratio_instead_of_changing_silently(hey):
    api = hey
    assert put(api, video_model=HEY["id"]).status_code == 422                       # resolusi bawaan 720p tidak didukung HeyGen
    assert put(api, video_model=HEY["id"], video_resolution="768p").status_code == 200
    assert settings(api)["video_resolution"] == "768p"
    assert put(api, aspect_ratio="9:21").status_code == 422 and settings(api)["aspect_ratio"] == "16:9"
    assert put(api, video_resolution="2K").status_code == 200


def hey_scene(api, with_cast=True):
    assert put(api, video_model=HEY["id"], video_resolution="480p").status_code == 200
    img = up(api)
    loc = api.post("/api/locations", json={"name": "Ruang", "description": "hangat", "image_id": img}).json()["id"]
    cid, _ = char(api, name="Momon")
    sid = scene(api, film(api))["id"]
    put_scene(api, sid, location_id=loc, planned_seconds=3, cast=[{"character_id": cid, "outfit_id": None, "action": "melompat"}])
    api.put(f"/api/scenes/{sid}/beats", json={"beats": [{"start": 0, "end": 3, "action": "masuk", "cast": [cid]}]})
    return sid


def test_preview_estimate_and_request_for_heygen(hey, fake):
    api = hey
    sid = hey_scene(api)
    pv = api.get(f"/api/scenes/{sid}/storyboard-video/preview").json()
    assert pv["duration"] == 5 and any("HeyGen minimal 5" in w for w in pv["warnings"])           # 3 dtk dibulatkan ke 5
    assert [r["kind"] for r in pv["refs"]] == ["image", "image"] and pv["audio_refs"] == 0
    est = api.raw.post("/api/estimate", json={"kind": "storyboard_video", "model": HEY["id"], "scene_id": sid}).json()
    assert est["high"] == pytest.approx(5 * 0.07 + 2 * 0.04)
    assert api.raw.post(f"/api/scenes/{sid}/storyboard-video", json={}).status_code == 409
    r = api.raw.post(f"/api/scenes/{sid}/storyboard-video", json={"confirmed_cost": est["high"]})
    assert r.status_code == 200, r.text
    req = last_video_request(fake)
    assert req["model"] == HEY["id"] and "generate_audio" not in req and len(req["input_references"]) == 2 and req["duration"] == 5


def test_previs_is_refused_for_heygen(hey):
    api = hey
    sid = hey_scene(api)
    r = api.raw.get(f"/api/scenes/{sid}/storyboard-video/preview?use_previs=true")
    assert r.status_code == 422 and "HeyGen tidak mendukung previs" in r.json()["detail"]
