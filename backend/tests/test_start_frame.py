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
    assert api.raw.put(f"/api/scenes/{s1}", json={"start_from_scene_id": s1}).status_code == 422                 # dirinya sendiri
    assert api.raw.put(f"/api/scenes/{s2}", json={"start_from_scene_id": "tidak-ada"}).status_code == 422
    r = api.raw.put(f"/api/scenes/{s2}", json={"start_from_scene_id": s1})
    assert r.status_code == 200 and (r.json()["start_from_scene_id"], r.json()["start_from_number"]) == (s1, 1)
    assert api.raw.put(f"/api/scenes/{s2}", json={"start_from_scene_id": None}).json()["start_from_number"] is None


def test_without_a_finished_previous_video_preview_warns_but_generate_and_estimate_refuse(sb, fake):
    api, s1, s2, cid = two_scenes(sb)
    api.put(f"/api/scenes/{s2}", json={"start_from_scene_id": s1})
    pv = api.get(f"/api/scenes/{s2}/storyboard-video/preview").json()
    assert pv["start_from_scene_id"] == s1 and pv["start_frame"] is None and pv["start_info"]["ok"] is False
    assert "adegan 1 belum punya video" in pv["start_info"]["reason"] and any("tanpa frame awal" in w for w in pv["warnings"])
    assert api.raw.post("/api/estimate", json={"kind": "storyboard_video", "model": pv["model"], "scene_id": s2}).status_code == 422
    n = len(video_posts(fake))
    assert api.raw.post(f"/api/scenes/{s2}/storyboard-video", json={"confirmed_cost": 9}).status_code == 422
    assert len(video_posts(fake)) == n and frames(api) == []


def test_start_frame_is_sent_as_first_frame_without_references(sb, fake):
    api, s1, s2, cid = two_scenes(sb)
    make_video_for(api, s1)
    api.put(f"/api/scenes/{s2}", json={"start_from_scene_id": s1})
    pv = api.get(f"/api/scenes/{s2}/storyboard-video/preview").json()
    assert pv["start_info"]["ok"] and pv["start_frame"]["scene_number"] == 1
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
    api.put(f"/api/scenes/{s2}", json={"start_from_scene_id": s1})
    est = estimate(api, s2)
    fake.video_submit_error = "moderasi"
    assert api.raw.post(f"/api/scenes/{s2}/storyboard-video", json={"confirmed_cost": est["high"]}).status_code >= 400
    assert frames(api) == []


def test_previs_cannot_be_combined_and_unchecking_restores_references(sb, fake):
    api, s1, s2, cid = two_scenes(sb)
    make_video_for(api, s1)
    api.put(f"/api/scenes/{s2}", json={"start_from_scene_id": s1})
    assert api.raw.get(f"/api/scenes/{s2}/storyboard-video/preview?use_previs=true").status_code == 422
    api.put(f"/api/scenes/{s2}", json={"start_from_scene_id": None})
    pv = api.get(f"/api/scenes/{s2}/storyboard-video/preview").json()
    assert [r["kind"] for r in pv["refs"]] == ["image", "image"] and "@image_1" in pv["prompt"] and pv["start_frame"] is None


def test_deleting_the_source_scene_clears_the_choice(sb):
    api, s1, s2, cid = two_scenes(sb)
    make_video_for(api, s1)
    api.put(f"/api/scenes/{s2}", json={"start_from_scene_id": s1})
    api.raw.delete(f"/api/scenes/{s1}")
    sc = api.get(f"/api/films/{api.get('/api/films').json()[0]['id']}").json()["scenes"][0]
    assert sc["id"] == s2 and sc["start_from_scene_id"] is None and sc["start_from_number"] is None
    pv = api.get(f"/api/scenes/{s2}/storyboard-video/preview").json()
    assert pv["start_frame"] is None and [r["kind"] for r in pv["refs"]] == ["image", "image"]


def test_any_scene_of_the_episode_can_be_the_source_and_number_follows_reordering(sb, fake):
    api, s1, s2, cid = two_scenes(sb)
    f = api.get("/api/films").json()[0]["id"]
    s3 = scene(api, f)["id"]
    loc = api.get(f"/api/films/{f}").json()["scenes"][0]["location"]["id"]
    put(api, s3, location_id=loc, planned_seconds=5, cast=[{"character_id": cid, "outfit_id": None, "action": ""}])
    api.put(f"/api/scenes/{s3}/beats", json={"beats": [{"start": 0, "end": 3, "action": "Momon lari", "cast": [cid]}, {"start": 3, "end": 5, "action": "Momon jatuh", "cast": [cid]}]})
    make_video_for(api, s1)
    assert api.raw.put(f"/api/scenes/{s3}", json={"start_from_scene_id": s1}).status_code == 200        # adegan 3 melanjutkan dari adegan 1 (bukan 2)
    pv = api.get(f"/api/scenes/{s3}/storyboard-video/preview").json()
    assert pv["start_frame"]["scene_number"] == 1 and pv["start_frame"]["clip_id"]
    cands = {c["number"]: c for c in pv["start_candidates"]}
    assert set(cands) == {1, 2} and cands[1]["ok"] and not cands[2]["ok"] and "belum punya video" in cands[2]["reason"]
    est = estimate(api, s3)
    assert api.raw.post(f"/api/scenes/{s3}/storyboard-video", json={"confirmed_cost": est["high"]}).status_code == 200
    clip = api.studio.db.one("SELECT params FROM clips WHERE scene_id = ? ORDER BY created_at DESC", (s3,))
    assert json.loads(clip["params"])["start_from"]["scene_number"] == 1
    assert api.raw.put(f"/api/films/{f}/scene-order", json={"scene_ids": [s2, s1, s3]}).status_code == 200                       # nomor sumber bergeser, id tetap
    sc = {x["id"]: x for x in api.get(f"/api/films/{f}").json()["scenes"]}
    assert sc[s3]["start_from_scene_id"] == s1 and sc[s3]["start_from_number"] == 2


def test_bulk_delete_clears_choices_pointing_to_deleted_scenes(sb):
    api, s1, s2, cid = two_scenes(sb)
    f = api.get("/api/films").json()[0]["id"]
    api.put(f"/api/scenes/{s2}", json={"start_from_scene_id": s1})
    assert api.raw.post(f"/api/films/{f}/scenes/bulk-delete", json={"scene_ids": [s1]}).status_code == 200
    assert api.get(f"/api/films/{f}").json()["scenes"][0]["start_from_scene_id"] is None


def test_migration_v18_to_v19_maps_previous_flag_to_previous_scene_id(tmp_path):
    from app.db import Database
    db = Database(tmp_path / "m.db")
    now = "2026-01-01T00:00:00"
    db.execute("INSERT INTO workspaces (id, name, created_at, updated_at) VALUES ('w','w',?,?)", (now, now)) if False else None
    db._conn.execute("INSERT INTO films (id, title, created_at, updated_at, workspace_id) VALUES ('f','t',?,?,'main')", (now, now))
    for i, flag in enumerate((0, 1, 1)):
        db._conn.execute("INSERT INTO scenes (id, film_id, position, created_at, updated_at, start_from_prev) VALUES (?, 'f', ?, ?, ?, ?)", (f"s{i}", i, now, now, flag))
    db._conn.execute("UPDATE scenes SET start_from_scene_id = NULL")
    db._conn.execute("PRAGMA user_version = 18")
    db._conn.commit()
    db._migrate()
    got = {r["id"]: r["start_from_scene_id"] for r in db._conn.execute("SELECT id, start_from_scene_id FROM scenes")}
    assert got == {"s0": None, "s1": "s0", "s2": "s1"} and db._conn.execute("PRAGMA user_version").fetchone()[0] == 20
