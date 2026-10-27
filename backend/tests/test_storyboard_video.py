"""Plan 18 fase D: perakit request Seedance (murni) dan generate video adegan Storyboard v2 (OpenRouter palsu, tanpa biaya nyata)."""
import dataclasses
import json
import time
from pathlib import Path

import pytest

from app import seedance_request as sr
from app.openrouter import OpenRouterError
from test_scenes import film, put, scene
from test_voices_beats import add_voice, sine
from test_workspaces import char, hdr, mkws, up

SEED = {"id": "bytedance/seedance-2.0-mini", "supported_durations": list(range(4, 16)), "supported_resolutions": ["480p", "720p"],
        "supported_aspect_ratios": ["16:9", "9:16"], "generate_audio": True, "pricing_skus": {"duration_seconds": "0.05"}}


# ---------- perakit murni ----------
def cast(*names):
    return [{"character_id": n.lower(), "name": n, "description": f"{n} si tokoh", "image_id": f"img-{n.lower()}"} for n in names]


def beat(start, end, **kw):
    return {"start": start, "end": end, "action": "", "camera": "", "cast": [], "dialogue": [], "image_id": None, **kw}


def test_references_are_numbered_beats_then_characters_then_location():
    out = sr.build(beats=[beat(0, 3, image_id="b1", action="masuk", camera="wide"), beat(3, 6, action="duduk"), beat(6, 9, image_id="b3")],
                   cast=cast("Momon", "Sari"), location={"name": "Ruang", "description": "", "image_id": "loc"}, voices={}, style="kartun 2D")
    assert [(r["kind"], r["n"], r.get("image_id")) for r in out["refs"]] == [
        ("image", 1, "b1"), ("image", 2, "b3"), ("image", 3, "img-momon"), ("image", 4, "img-sari"), ("image", 5, "loc")]
    p = out["prompt"]
    assert "FORMAT: 9s / 3 SHOTS" in p and "MOOD: kartun 2D." in p
    assert "@image_1 — keyframe of shot 1" in p and "@image_2 — keyframe of shot 3" in p
    assert "SUBJECT: @image_3 — Momon, Momon si tokoh. @image_4 — Sari, Sari si tokoh." in p and "ENVIRONMENT: Ruang. Reference: @image_5." in p
    assert "SHOT 1 — 0:00 to 0:03, wide. masuk. Match @image_1." in p and "SHOT 2 — 0:03 to 0:06. duduk." in p and "SHOT 3 — 0:06 to 0:09. Match @image_2." in p
    assert out["warnings"] == []


def test_dialogue_voices_and_audio_cap():
    c = cast("Momon", "Sari", "Budi", "Ani")
    voices = {x["character_id"]: {"description": f"suara {x['name']}", "has_audio": True, "voice_id": f"v-{x['character_id']}"} for x in c}
    b = [beat(0, 4, dialogue=[{"character_id": x["character_id"], "text": f"Halo dari {x['name']}"} for x in c], cast=[x["character_id"] for x in c])]
    out = sr.build(beats=b, cast=c, location=None, voices=voices)
    audio = [r for r in out["refs"] if r["kind"] == "audio"]
    assert [r["n"] for r in audio] == [1, 2, 3] and [r["voice_id"] for r in audio] == ["v-momon", "v-sari", "v-budi"]
    assert "@audio_1 — the voice of Momon" in out["prompt"] and 'Ani says: "Halo dari Ani"' in out["prompt"]
    assert "Ani's voice: suara Ani." in out["prompt"]                       # lewat batas 3 sampel -> deskripsi teks
    assert any("hanya 3 sampel suara" in w for w in out["warnings"])


def test_without_public_hosting_samples_become_text_with_a_warning():
    c = cast("Momon")
    v = {"momon": {"description": "berat", "has_audio": True, "voice_id": "v1"}}
    out = sr.build(beats=[beat(0, 4, dialogue=[{"character_id": "momon", "text": "yo"}])], cast=c, location=None, voices=v, use_audio=False)
    assert not [r for r in out["refs"] if r["kind"] == "audio"] and "Momon's voice: berat." in out["prompt"]
    v2 = {"momon": {"description": "", "has_audio": True, "voice_id": "v1"}}
    out = sr.build(beats=[beat(0, 4, dialogue=[{"character_id": "momon", "text": "yo"}])], cast=c, location=None, voices=v2, use_audio=False)
    assert any("tanpa hosting publik" in w for w in out["warnings"])


def test_image_cap_never_drops_beat_images_first_and_thins_evenly():
    many = [beat(i, i + 1, image_id=f"b{i}") for i in range(12)]
    out = sr.build(beats=many, cast=cast("Momon"), location={"name": "L", "description": "", "image_id": "loc"}, voices={})
    imgs = [r for r in out["refs"] if r["kind"] == "image"]
    assert len(imgs) == sr.MAX_IMAGES and imgs[0]["image_id"] == "b0" and imgs[-1]["image_id"] == "b11"   # awal & akhir dijaga
    assert all(r["image_id"].startswith("b") for r in imgs)                                              # tak ada tempat tersisa untuk karakter/latar
    assert any("3 gambar beat tidak dikirim" in w for w in out["warnings"]) and any("Momon" in w for w in out["warnings"])
    assert out["prompt"].count("SHOT ") >= 12                                                             # semua beat tetap ada di teks
    # tempat tersisa: karakter didahulukan atas latar
    out = sr.build(beats=[beat(i, i + 1, image_id=f"b{i}") for i in range(8)], cast=cast("Momon", "Sari"),
                   location={"name": "L", "description": "", "image_id": "loc"}, voices={})
    assert [r["image_id"] for r in out["refs"]][-1] == "img-momon" and any("latar L" in w for w in out["warnings"])


def test_no_beats_uses_fallback_and_previs_adds_video_reference():
    out = sr.build(beats=[], cast=cast("Momon"), location=None, voices={}, fallback_action="Momon: berlari", previs=True)
    assert "Momon: berlari" in out["prompt"] and out["refs"][-1] == {"kind": "video", "n": 1, "label": "video previs 3D"}
    assert "@video_1" in out["prompt"]


# ---------- layanan ----------
@pytest.fixture
def sb(api):
    api.studio._models = (time.time(), [*api.studio.video_models(), SEED])
    api.put("/api/workspaces/main/settings", json={"video_model": SEED["id"], "video_resolution": "720p", "style": "kartun 2D"})
    img = up(api)
    loc = api.post("/api/locations", json={"name": "Ruang", "description": "hangat", "image_id": img}).json()["id"]
    cid, _ = char(api, name="Momon")
    f = film(api)
    sid = scene(api, f)["id"]
    put(api, sid, location_id=loc, planned_seconds=9, cast=[{"character_id": cid, "outfit_id": None, "action": "melompat"}])
    api.put(f"/api/scenes/{sid}/beats", json={"beats": [
        {"start": 0, "end": 4, "action": "masuk", "camera": "wide", "cast": [cid]},
        {"start": 4, "end": 9, "action": "bicara", "cast": [cid], "dialogue": [{"character_id": cid, "text": "Aku lapar"}]}]})
    return api, sid, cid


def last_video_request(fake):
    posts = [r for r in fake.requests if r.method == "POST" and r.url.path.endswith("/videos")]
    return json.loads(posts[-1].content)


def estimate(api, sid):
    return api.raw.post("/api/estimate", json={"kind": "storyboard_video", "model": SEED["id"], "scene_id": sid}).json()


def test_preview_estimate_and_generate_payload(sb, fake):
    api, sid, cid = sb
    pv = api.get(f"/api/scenes/{sid}/storyboard-video/preview").json()
    assert pv["model"] == SEED["id"] and pv["duration"] == 9 and pv["resolution"] == "720p" and pv["aspect_ratio"] == "16:9"
    assert [r["kind"] for r in pv["refs"]] == ["image", "image"] and "SHOT 2" in pv["prompt"] and "Visual style: kartun 2D." in pv["prompt"]
    est = estimate(api, sid)
    assert est["high"] == pytest.approx(0.45) and est["blocked"] is None
    assert api.raw.post(f"/api/scenes/{sid}/storyboard-video", json={}).status_code == 409            # konfirmasi biaya wajib
    r = api.raw.post(f"/api/scenes/{sid}/storyboard-video", json={"confirmed_cost": est["high"]})
    assert r.status_code == 200, r.text
    req = last_video_request(fake)
    assert req["model"] == SEED["id"] and req["duration"] == 9 and req["resolution"] == "720p" and req["aspect_ratio"] == "16:9"
    assert [x["type"] for x in req["input_references"]] == ["image_url", "image_url"]
    assert all(x["image_url"]["url"].startswith("data:image/jpeg;base64,") for x in req["input_references"])
    assert "@image_1 — Momon" in req["prompt"] and 'Momon says: "Aku lapar"' in req["prompt"]
    scene_json = r.json()
    assert scene_json["clip_id"] and scene_json["video_takes"]
    row = api.studio.db.one("SELECT kind, params, estimated_cost FROM clips WHERE id = ?", (scene_json["clip_id"],))
    assert row["kind"] == "storyboard" and json.loads(row["params"])["mode"] == "storyboard" and row["estimated_cost"] == pytest.approx(0.45)


def test_job_and_daily_limits_do_not_block_but_stale_confirmation_does(sb):
    api, sid, _ = sb
    api.studio.s = dataclasses.replace(api.studio.s, max_cost_per_job=0.01, daily_budget_usd=0.02)
    est = estimate(api, sid)
    assert est["blocked"] is None
    assert api.raw.post(f"/api/scenes/{sid}/storyboard-video", json={"confirmed_cost": 0.01}).status_code == 409   # estimasi berubah
    assert api.raw.post(f"/api/scenes/{sid}/storyboard-video", json={"confirmed_cost": est["high"]}).status_code == 200


def test_scene_over_15_seconds_is_rejected_with_advice(sb):
    api, sid, cid = sb
    api.put(f"/api/scenes/{sid}/beats", json={"beats": [{"start": 0, "end": 10, "cast": [cid]}, {"start": 10, "end": 16}]})
    r = api.raw.get(f"/api/scenes/{sid}/storyboard-video/preview")
    assert r.status_code == 422 and "15 dtk" in r.json()["detail"] and r.json()["code"] == "scene_too_long"


def test_short_scene_is_rounded_up_and_prompt_can_be_overridden(sb, fake):
    api, sid, cid = sb
    api.put(f"/api/scenes/{sid}/beats", json={"beats": [{"start": 0, "end": 2.5, "cast": [cid]}]})
    pv = api.get(f"/api/scenes/{sid}/storyboard-video/preview").json()
    assert pv["duration"] == 4 and any("minimal 4 dtk" in w for w in pv["warnings"])
    est = estimate(api, sid)
    assert api.raw.post(f"/api/scenes/{sid}/storyboard-video", json={"confirmed_cost": est["high"], "prompt": "prompt sunting user"}).status_code == 200
    assert last_video_request(fake)["prompt"] == "prompt sunting user"


def test_project_model_and_workspace_are_respected(sb):
    api, sid, _ = sb
    b = mkws(api, "B")
    assert api.raw.get(f"/api/scenes/{sid}/storyboard-video/preview", **hdr(b)).status_code == 404         # adegan workspace lain
    assert api.raw.post(f"/api/scenes/{sid}/storyboard-video", json={"confirmed_cost": 1}, **hdr(b)).status_code == 404
    api.studio.db.execute("UPDATE workspaces SET video_model = 'bytedance/seedance-2.5' WHERE id = 'main'")   # data lama/bypass: tetap ditolak
    assert api.raw.get(f"/api/scenes/{sid}/storyboard-video/preview").status_code == 422


class StubPublic:
    def __init__(self):
        self.published, self.deleted = [], []

    def publish(self, path, content_type="video/mp4"):
        self.published.append((Path(path).name, content_type))
        return f"key{len(self.published)}", f"https://pub.test/{len(self.published)}.m4a"

    def delete(self, key):
        self.deleted.append(key)


def test_voice_sample_goes_as_audio_reference_and_key_is_released_after_job(sb, fake, tmp_path):
    api, sid, cid = sb
    add_voice(api, cid, file=sine(tmp_path, 3), consent="true", description="berat")
    stub = api.studio.public = StubPublic()
    pv = api.get(f"/api/scenes/{sid}/storyboard-video/preview").json()
    assert pv["public_media"] and pv["audio_refs"] == 1 and "@audio_1 — the voice of Momon" in pv["prompt"]
    est = estimate(api, sid)
    assert api.raw.post(f"/api/scenes/{sid}/storyboard-video", json={"confirmed_cost": est["high"]}).status_code == 200
    req = last_video_request(fake)
    assert [x["type"] for x in req["input_references"]] == ["image_url", "image_url", "audio_url"]
    assert req["input_references"][2]["audio_url"]["url"] == "https://pub.test/1.m4a" and stub.published[0][1] == "audio/mp4"
    assert stub.deleted == []                                                                           # masih dimiliki job yang berjalan
    api.studio.poll_once()                                                                              # job selesai -> kunci dilepas
    assert stub.deleted == ["key1"]


def test_audio_rejected_by_provider_retries_without_audio(sb, tmp_path, monkeypatch):
    api, sid, cid = sb
    add_voice(api, cid, file=sine(tmp_path, 3), consent="true", description="berat")
    stub = api.studio.public = StubPublic()
    real, calls = api.studio.client.submit_video, []

    def flaky(payload):
        calls.append(payload)
        if any(r["type"] == "audio_url" for r in payload["input_references"]):
            raise OpenRouterError("input_references: audio not supported", 400)
        return real(payload)
    monkeypatch.setattr(api.studio.client, "submit_video", flaky)
    est = estimate(api, sid)
    r = api.raw.post(f"/api/scenes/{sid}/storyboard-video", json={"confirmed_cost": est["high"]})
    assert r.status_code == 200, r.text
    assert len(calls) == 2 and not any(x["type"] == "audio_url" for x in calls[1]["input_references"])
    assert "Momon's voice: berat." in calls[1]["prompt"] and "@audio_" not in calls[1]["prompt"]
    clip = api.studio.db.one("SELECT params FROM clips ORDER BY created_at DESC LIMIT 1")
    assert json.loads(clip["params"]).get("audio_ref_dropped") is True
    api.studio.poll_once()
    assert stub.deleted == ["key1"]                                                                     # file publik dilepas saat job selesai


def test_provider_rejection_creates_no_clip_and_releases_published_files(sb, fake, tmp_path):
    api, sid, cid = sb
    add_voice(api, cid, file=sine(tmp_path, 3), consent="true")
    stub = api.studio.public = StubPublic()
    fake.video_submit_error = "ditolak penyedia"
    est = estimate(api, sid)
    r = api.raw.post(f"/api/scenes/{sid}/storyboard-video", json={"confirmed_cost": est["high"]})
    assert r.status_code >= 400 and api.studio.db.one("SELECT COUNT(*) AS n FROM clips WHERE kind = 'storyboard'")["n"] == 0
    assert stub.deleted == ["key1"]                                                                     # tidak ada file publik yang tertinggal


def test_full_format_global_block_wardrobe_genre_size_lens_and_timestamps():
    c = cast("Momon")
    c[0]["wardrobe"] = "jaket merah"
    out = sr.build(beats=[beat(0, 2.5, size="WS", lens="24", camera="locked", action="Momon masuk"),
                          beat(2.5, 65, size="CU", lens="85", camera="slow push-in", action="menatap",
                               cast=["momon"], dialogue=[{"character_id": "momon", "text": "Halo"}])],
                   cast=c, location={"name": "Dapur", "description": "marmer", "image_id": None}, voices={}, style="noir", genre="heist",
                   mood="tegang")
    p = out["prompt"]
    assert p.startswith("FORMAT: 65s / 2 SHOTS / heist\nSUBJECT: @image_1 — Momon, Momon si tokoh.\nWARDROBE: Momon: jaket merah.\n"
                        "ENVIRONMENT: Dapur. marmer.\nMOOD: tegang.")
    assert "SHOT 1 — 0:00 to 0:02.5, WS, 24mm, locked. Momon masuk." in p
    assert 'SHOT 2 — 0:02.5 to 1:05, CU, 85mm, slow push-in. menatap. Momon says: "Halo".' in p
    assert "WARDROBE" not in sr.build(beats=[], cast=cast("Momon"), location=None, voices={}, fallback_action="x")["prompt"]
