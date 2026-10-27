from conftest import upload

M = "openai/gpt-image-2"


def make_char(api):
    src = upload(api)
    r = api.raw.post("/api/characters", json={"name": "Rina", "description": "young woman, short black bob, red jacket",
                                              "source_image_id": src["id"]})
    assert r.status_code == 200, r.text
    return src, r.json()


def test_create_and_list_character(api):
    src, ch = make_char(api)
    assert ch["images"] == [{"image_id": src["id"], "label": "source"}]
    assert api.get("/api/characters").json()[0]["id"] == ch["id"]
    assert api.raw.post("/api/characters", json={"name": " ", "description": "x", "source_image_id": src["id"]}).status_code == 400
    assert api.raw.post("/api/characters", json={"name": "x", "description": "x", "source_image_id": "nope"}).status_code == 404


def sheet_posts(fake):
    return [x for x in fake.requests if x.url.path.endswith("/images") and x.method == "POST"]


def test_sheet_is_one_image_with_several_angles_and_needs_confirmation(api, fake):
    src, ch = make_char(api)
    est = api.raw.post("/api/estimate", json={"kind": "character_sheet", "model": M}).json()
    assert est["high"] == 0.02                        # SATU gambar x $0,02
    n = len(sheet_posts(fake))
    assert api.raw.post(f"/api/characters/{ch['id']}/sheet", json={"model": M}).status_code == 409   # tanpa konfirmasi tidak ada panggilan
    assert len(sheet_posts(fake)) == n
    r = api.raw.post(f"/api/characters/{ch['id']}/sheet", json={"model": M, "confirmed_cost": est["high"]})
    assert r.status_code == 200, r.text
    assert [i["label"] for i in r.json()["images"]] == ["source", "sheet"]
    calls = sheet_posts(fake)[n:]
    assert len(calls) == 1                            # satu panggilan, bukan empat
    prompt = __import__("json").loads(calls[0].content)["prompt"]
    for angle in ("front view", "three-quarter view", "side profile view", "back view"):
        assert angle in prompt
    assert "ONE single image" in prompt and "No text" in prompt and "red jacket" in prompt and "identical" in prompt
    assert sum(1 for i in api.get("/api/images").json() if i["kind"] == "sheet") == 1
    assert api.studio.db.committed_today() >= 0.01


def test_sheet_asks_for_wide_ratio_only_when_model_supports_it(api, fake):
    src, ch = make_char(api)
    n = len(sheet_posts(fake))
    api.raw.post(f"/api/characters/{ch['id']}/sheet", json={"model": M, "confirmed_cost": 0.02})
    body = __import__("json").loads(sheet_posts(fake)[n].content)
    supported = "16:9" in (((next(m for m in api.studio.image_models() if m["id"] == M).get("supported_parameters") or {}).get("aspect_ratio") or {}).get("values") or [])
    assert (body.get("aspect_ratio") == "16:9") == supported


def test_sheet_respects_per_job_limit(api, settings):
    src, ch = make_char(api)
    api.studio.s = type(settings)(**{**settings.__dict__, "max_cost_per_job": 0.01})
    r = api.raw.post(f"/api/characters/{ch['id']}/sheet", json={"model": M, "confirmed_cost": 0.02})
    assert r.status_code == 402


def test_edit_with_character_adds_sheet_references_and_description(api, fake):
    src, ch = make_char(api)
    extra = upload(api)
    api.raw.post(f"/api/characters/{ch['id']}/images", json={"image_id": extra["id"], "label": "front"})
    target = upload(api)
    r = api.post(f"/api/images/{target['id']}/edit", json={"prompt": "put her in a forest", "model": M,
                                                           "character_id": ch["id"]})
    assert r.status_code == 200, r.text
    body = fake.last_json("/images")
    assert len(body["input_references"]) == 1 + 2      # sumber + 2 gambar karakter
    assert "short black bob" in body["prompt"] and "put her in a forest" in body["prompt"]


def test_edit_with_unknown_character_404(api):
    target = upload(api)
    r = api.raw.post(f"/api/images/{target['id']}/edit", json={"prompt": "x", "model": M, "character_id": "nope"})
    assert r.status_code == 404


def test_database_reaches_latest_version(tmp_path):
    from app.db import Database
    db = Database(tmp_path / "x.db")
    assert db.one("PRAGMA user_version")["user_version"] == 18
