"""Plan 18 Revisi 9: adegan ke-2 dst. bisa mulai dari frame akhir video adegan sebelumnya."""
import json

from test_scenes import put, scene
from test_storyboard_video import estimate, last_video_request, sb  # noqa: F401  (fixture sb)


def two_scenes(sb):
    api, s1, cid = sb
    f = api.get("/api/films").json()[0]["id"]
    s2 = scene(api, f)["id"]
    loc = api.get(f"/api/films/{f}").json()["scenes"][0]["location"]["id"]
    put(api, s2, location_id=loc, planned_seconds=6, cast=[{"character_id": cid, "outfit_id": None, "action": ""}])
    api.put(f"/api/scenes/{s2}/beats", json={"beats": [{"start": 0, "end": 3, "action": "Momon duduk", "cast": [cid]},
                                                      {"start": 3, "end": 6, "action": "Momon tidur", "cast": [cid]}]})
    return api, s1, s2, cid


def make_video_for(api, sid):
    est = estimate(api, sid)
    assert api.raw.post(f"/api/scenes/{sid}/storyboard-video", json={"confirmed_cost": est["high"]}).status_code == 200
    api.studio.poll_once()


def frames(api):
    return [i for i in api.get("/api/images").json() if i["kind"] == "frame"]


def video_posts(fake):
    return [r for r in fake.requests if r.method == "POST" and r.url.path.endswith("/videos")]


def test_flag_is_validated_and_not_allowed_on_first_scene(sb):
    api, s1, s2, cid = two_scenes(sb)
    assert api.raw.put(f"/api/scenes/{s1}", json={"start_from_prev": True}).status_code == 422
    assert api.raw.put(f"/api/scenes/{s2}", json={"start_from_prev": "ya"}).status_code == 422
    r = api.raw.put(f"/api/scenes/{s2}", json={"start_from_prev": True})
    assert r.status_code == 200 and r.json()["start_from_prev"] is True


def test_without_a_finished_previous_video_preview_warns_but_generate_and_estimate_refuse(sb, fake):
    api, s1, s2, cid = two_scenes(sb)
    api.put(f"/api/scenes/{s2}", json={"start_from_prev": True})
    pv = api.get(f"/api/scenes/{s2}/storyboard-video/preview").json()
    assert pv["start_from_prev"] and pv["start_frame"] is None and pv["can_start_from_prev"]["ok"] is False
    assert "adegan 1 belum punya video" in pv["can_start_from_prev"]["reason"] and any("tanpa frame awal" in w for w in pv["warnings"])
    assert api.raw.post("/api/estimate", json={"kind": "storyboard_video", "model": pv["model"], "scene_id": s2}).status_code == 422
    n = len(video_posts(fake))
    assert api.raw.post(f"/api/scenes/{s2}/storyboard-video", json={"confirmed_cost": 9}).status_code == 422
    assert len(video_posts(fake)) == n and frames(api) == []


def test_start_frame_is_sent_as_first_frame_without_references(sb, fake):
    api, s1, s2, cid = two_scenes(sb)
    make_video_for(api, s1)
    api.put(f"/api/scenes/{s2}", json={"start_from_prev": True})
    pv = api.get(f"/api/scenes/{s2}/storyboard-video/preview").json()
    assert pv["can_start_from_prev"]["ok"] and pv["start_frame"]["scene_number"] == 1
    assert [r["kind"] for r in pv["refs"]] == ["frame"] and pv["audio_refs"] == 0
    assert "Start exactly from the provided first frame" in pv["prompt"] and "@image_" not in pv["prompt"] and "@[" not in pv["prompt"] and "Momon duduk" in pv["prompt"]
    assert pv["prompt"].index("Visual style: kartun 2D.") < pv["prompt"].index("SHOT 1")
    assert any("tidak dikirim" in w for w in pv["warnings"])
    est = estimate(api, s2)
    assert est["high"] > 0 and est["blocked"] is None
    assert api.raw.post(f"/api/scenes/{s2}/storyboard-video", json={}).status_code == 409           # konfirmasi tetap wajib
    r = api.raw.post(f"/api/scenes/{s2}/storyboard-video", json={"confirmed_cost": est["high"]})
    assert r.status_code == 200, r.text
    req = last_video_request(fake)
    assert "input_references" not in req
    assert len(req["frame_images"]) == 1 and req["frame_images"][0]["frame_type"] == "first_frame"
    assert req["frame_images"][0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert len(frames(api)) == 1
    clip = api.studio.db.one("SELECT * FROM clips WHERE scene_id = ? ORDER BY created_at DESC", (s2,))
    params = json.loads(clip["params"])
    assert params["start_from"]["scene_number"] == 1 and params["start_from"]["image_id"] == clip["source_image_id"] == frames(api)[0]["id"]


def test_provider_rejection_leaves_no_orphan_frame(sb, fake):
    api, s1, s2, cid = two_scenes(sb)
    make_video_for(api, s1)
    api.put(f"/api/scenes/{s2}", json={"start_from_prev": True})
    est = estimate(api, s2)
    fake.video_submit_error = "moderasi"
    assert api.raw.post(f"/api/scenes/{s2}/storyboard-video", json={"confirmed_cost": est["high"]}).status_code >= 400
    assert frames(api) == []


def test_previs_cannot_be_combined_and_unchecking_restores_references(sb, fake):
    api, s1, s2, cid = two_scenes(sb)
    make_video_for(api, s1)
    api.put(f"/api/scenes/{s2}", json={"start_from_prev": True})
    assert api.raw.get(f"/api/scenes/{s2}/storyboard-video/preview?use_previs=true").status_code == 422
    api.put(f"/api/scenes/{s2}", json={"start_from_prev": False})
    pv = api.get(f"/api/scenes/{s2}/storyboard-video/preview").json()
    assert [r["kind"] for r in pv["refs"]] == ["image", "image"] and "@image_1" in pv["prompt"] and pv["start_frame"] is None


def test_previous_scene_is_resolved_by_current_order(sb):
    api, s1, s2, cid = two_scenes(sb)
    make_video_for(api, s1)
    api.put(f"/api/scenes/{s2}", json={"start_from_prev": True})
    f = api.get("/api/films").json()[0]["id"]
    api.raw.delete(f"/api/scenes/{s1}")                       # s2 menjadi adegan pertama
    pv = api.get(f"/api/scenes/{s2}/storyboard-video/preview").json()
    assert pv["start_frame"] is None and "tidak tersedia" in " ".join(pv["warnings"])
    assert api.raw.post(f"/api/scenes/{s2}/storyboard-video", json={"confirmed_cost": 9}).status_code == 422
