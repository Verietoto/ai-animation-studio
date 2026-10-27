from test_scenes import film, put, scene
from test_workspaces import VIDEO, char, up

IMG_MODEL = "openai/gpt-image-2"          # tiruan: menerima maks 3 gambar input, rasio 1:1 / 16:9 / auto
VIDEO_MODEL = VIDEO["model"]


def estimate(api, **body):
    r = api.raw.post("/api/estimate", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def with_image_location(api, name="Sawah"):
    loc = api.post("/api/locations", json={"name": name, "description": "pematang, kabut", "image_id": up(api)}).json()
    return loc["id"]


def ready_scene(api, cast_names=("Rani",), aspect=None):
    """Adegan dengan latar bergambar dan pemeran; kembalikan (film_id, scene_id, [character_id])."""
    f = film(api)
    if aspect:
        api.put(f"/api/films/{f}", json={"aspect_ratio": aspect})
    s = scene(api, f)["id"]
    ids = [char(api, name=n)[0] for n in cast_names]
    put(api, s, location_id=with_image_location(api), time_of_day="senja", camera="dolly in",
        cast=[{"character_id": c, "action": f"aksi {i}"} for i, c in enumerate(ids)])
    return f, s, ids


def keyframe(api, scene_id, **kw):
    est = estimate(api, kind="scene_keyframe", model=IMG_MODEL, scene_id=scene_id)
    return api.raw.post(f"/api/scenes/{scene_id}/keyframe", json={"model": IMG_MODEL, "confirmed_cost": est["high"], **kw})


# ---------- latar dari teks ----------
def test_location_image_from_text_sends_no_input_references(api, fake):
    loc = api.post("/api/locations", json={"name": "Pasar", "description": "ramai pagi hari"}).json()["id"]
    est = estimate(api, kind="location_image", model=IMG_MODEL, location_id=loc)
    assert est["high"] > 0
    assert api.raw.post(f"/api/locations/{loc}/image", json={"model": IMG_MODEL}).status_code == 409   # tanpa konfirmasi biaya
    r = api.raw.post(f"/api/locations/{loc}/image", json={"model": IMG_MODEL, "confirmed_cost": est["high"]})
    assert r.status_code == 200, r.text
    body = fake.last_json("/images")
    assert "input_references" not in body and "Pasar" in body["prompt"] and "No people" in body["prompt"]
    assert body.get("aspect_ratio") == "16:9"
    img = r.json()["image_id"]
    row = api.studio.db.one("SELECT kind, scene_id, cost FROM images WHERE id = ?", (img,))
    assert row["kind"] == "location" and row["scene_id"] is None and row["cost"] == 0.01


def test_location_image_rejects_unknown_model_and_foreign_location(api):
    loc = api.post("/api/locations", json={"name": "Pasar"}).json()["id"]
    r = api.raw.post(f"/api/locations/{loc}/image", json={"model": "x/tidak-ada", "confirmed_cost": 1})
    assert r.status_code == 400
    assert api.raw.post("/api/locations/nope/image", json={"model": IMG_MODEL, "confirmed_cost": 1}).status_code == 404


# ---------- keyframe ----------
def test_keyframe_needs_location_with_image(api):
    f = film(api)
    s = scene(api, f)["id"]
    assert api.raw.post("/api/estimate", json={"kind": "scene_keyframe", "model": IMG_MODEL, "scene_id": s}).status_code == 422
    put(api, s, location_id=api.post("/api/locations", json={"name": "Tanpa gambar"}).json()["id"])
    r = api.raw.post("/api/estimate", json={"kind": "scene_keyframe", "model": IMG_MODEL, "scene_id": s})
    assert r.status_code == 422 and "belum punya gambar" in r.json()["detail"]


def test_keyframe_estimate_matches_generate_and_uses_scene_prompt(api, fake):
    f, s, _ = ready_scene(api, ("Rani", "Budi"))
    est = estimate(api, kind="scene_keyframe", model=IMG_MODEL, scene_id=s)
    assert est["inputs"] == 3                                               # latar + 2 pemeran
    r = keyframe(api, s)
    assert r.status_code == 200, r.text
    body = fake.last_json("/images")
    assert len(body["input_references"]) == est["inputs"]                  # estimasi = generate
    prompt = body["prompt"]
    assert prompt.startswith("Rani: aksi 0. Budi: aksi 1. Time: senja. Camera: dolly in.")
    assert "Image 1 is the LOCATION" in prompt and "CHARACTER Rani" in prompt and "CHARACTER Budi" in prompt
    assert "Do not swap the characters' faces or clothes." in prompt
    assert body["aspect_ratio"] == "16:9"                                   # rasio episode dikirim bila didukung
    scn = r.json()
    assert scn["status"] == "keyframe" and scn["keyframe_image_id"] and scn["keyframe_takes"] == [scn["keyframe_image_id"]]
    row = api.studio.db.one("SELECT kind, scene_id FROM images WHERE id = ?", (scn["keyframe_image_id"],))
    assert row == {"kind": "keyframe", "scene_id": s}


def test_keyframe_skips_unsupported_aspect_ratio(api, fake):
    _, s, _ = ready_scene(api, aspect="9:16")                               # tiruan hanya mendukung 1:1, 16:9, auto
    assert keyframe(api, s).status_code == 200
    assert "aspect_ratio" not in fake.last_json("/images")


def test_keyframe_respects_model_input_limit(api):
    _, s, _ = ready_scene(api, ("A", "B", "C"))                             # latar + 3 = 4 > 3
    r = api.raw.post("/api/estimate", json={"kind": "scene_keyframe", "model": IMG_MODEL, "scene_id": s})
    assert r.status_code == 400 and "maksimal 3" in r.json()["detail"]


def test_keyframe_requires_confirmation_and_exact_estimate(api):
    _, s, _ = ready_scene(api)
    assert api.raw.post(f"/api/scenes/{s}/keyframe", json={"model": IMG_MODEL}).status_code == 409
    assert api.raw.post(f"/api/scenes/{s}/keyframe", json={"model": IMG_MODEL, "confirmed_cost": 0.0001}).status_code == 409
    assert api.studio.db.one("SELECT COUNT(*) AS n FROM images WHERE kind = 'keyframe'")["n"] == 0


def test_second_keyframe_is_a_take_and_does_not_replace_selection(api):
    _, s, _ = ready_scene(api)
    first = keyframe(api, s).json()["keyframe_image_id"]
    scn = keyframe(api, s).json()
    assert scn["keyframe_image_id"] == first and len(scn["keyframe_takes"]) == 2
    other = scn["keyframe_takes"][0]
    assert put(api, s, keyframe_image_id=other).json()["keyframe_image_id"] == other      # user memilih take


def test_keyframe_uses_text_only_outfit_and_outfit_image(api, fake):
    _, s, (cid,) = ready_scene(api)
    text_outfit = api.post(f"/api/characters/{cid}/outfits", json={"name": "Jas", "description": "jas hujan kuning"}).json()["id"]
    put(api, s, cast=[{"character_id": cid, "outfit_id": text_outfit, "action": "berdiri"}])
    assert keyframe(api, s).status_code == 200
    assert "change the clothing to: jas hujan kuning" in fake.last_json("/images")["prompt"]
    pic_outfit = api.post(f"/api/characters/{cid}/outfits", json={"name": "Kebaya", "image_id": up(api, color=(1, 2, 3))}).json()["id"]
    put(api, s, cast=[{"character_id": cid, "outfit_id": pic_outfit, "action": "berdiri"}])
    assert keyframe(api, s).status_code == 200
    assert "change the clothing" not in fake.last_json("/images")["prompt"]


def test_keyframe_blocked_while_episode_renders(api):
    f, s, _ = ready_scene(api)
    est = estimate(api, kind="scene_keyframe", model=IMG_MODEL, scene_id=s)
    api.studio.db.update("films", f, {"render_status": "rendering"})
    assert api.raw.post(f"/api/scenes/{s}/keyframe", json={"model": IMG_MODEL, "confirmed_cost": est["high"]}).status_code == 409


# ---------- video ----------
def test_video_needs_keyframe(api):
    _, s, _ = ready_scene(api)
    r = api.raw.post("/api/estimate", json={"kind": "scene_video", "model": VIDEO_MODEL, "scene_id": s, "duration": 4})
    assert r.status_code == 422 and "keyframe" in r.json()["detail"]


def test_video_from_scene_sends_scene_prompt_and_episode_aspect(api, fake):
    _, s, _ = ready_scene(api)
    assert keyframe(api, s).status_code == 200
    est = estimate(api, kind="scene_video", model=VIDEO_MODEL, scene_id=s, duration=4, resolution="720p")
    r = api.raw.post(f"/api/scenes/{s}/video", json={"model": VIDEO_MODEL, "duration": 4, "resolution": "720p", "confirmed_cost": est["high"]})
    assert r.status_code == 200, r.text
    sent = fake.last_json("/videos")
    assert sent["prompt"] == "Rani: aksi 0. Time: senja. Camera: dolly in." and sent["aspect_ratio"] == "16:9"
    scn = r.json()
    assert scn["status"] == "video_diproses" and scn["clip_id"] and [t["id"] for t in scn["video_takes"]] == [scn["clip_id"]]
    assert api.studio.db.one("SELECT scene_id FROM clips WHERE id = ?", (scn["clip_id"],))["scene_id"] == s
    api.studio.poll_once()
    assert api.get(f"/api/films/{scn['film_id']}").json()["scenes"][0]["status"] == "siap"


def test_new_video_does_not_replace_a_good_selection_but_replaces_a_failed_one(api):
    _, s, _ = ready_scene(api)
    keyframe(api, s)

    def make():
        est = estimate(api, kind="scene_video", model=VIDEO_MODEL, scene_id=s, duration=4)
        r = api.raw.post(f"/api/scenes/{s}/video", json={"model": VIDEO_MODEL, "duration": 4, "confirmed_cost": est["high"]})
        assert r.status_code == 200, r.text
        return r.json()

    first = make()["clip_id"]
    second = make()
    assert second["clip_id"] == first and len(second["video_takes"]) == 2          # yang berjalan tidak ditimpa
    api.studio.db.update("clips", first, {"status": "failed"})
    third = make()
    assert third["clip_id"] == third["video_takes"][0]["id"] and third["clip_id"] != first   # yang gagal diganti take terbaru


# ---------- durasi rencana + pembersihan ----------
def test_planned_seconds_validation_and_episode_total(api):
    f = film(api)
    a, b = scene(api, f)["id"], scene(api, f)["id"]
    assert put(api, a, planned_seconds=8).json()["planned_seconds"] == 8
    assert put(api, b, planned_seconds=5).status_code == 200
    for bad in (0, 121, 2.5, "x"):
        assert put(api, a, planned_seconds=bad).status_code == 422, bad
    assert api.get(f"/api/films/{f}").json()["planned_seconds"] == 13
    assert put(api, a, planned_seconds=None).json()["planned_seconds"] is None
    assert api.get("/api/films").json()[0]["planned_seconds"] == 5
    dup = api.post(f"/api/scenes/{b}/duplicate").json()
    assert dup["planned_seconds"] == 5


def test_deleting_scene_keeps_takes_in_library(api):
    _, s, _ = ready_scene(api)
    img = keyframe(api, s).json()["keyframe_image_id"]
    assert api.delete(f"/api/scenes/{s}").status_code == 200
    row = api.studio.db.one("SELECT scene_id, deleted_at FROM images WHERE id = ?", (img,))
    assert row == {"scene_id": None, "deleted_at": None}
    assert api.get(f"/api/images/{img}/file").status_code == 200
