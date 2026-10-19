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


def test_sheet_requires_total_confirmation_then_creates_four_views(api, fake):
    src, ch = make_char(api)
    est = api.raw.post("/api/estimate", json={"kind": "character_sheet", "model": M}).json()
    assert est["high"] == 0.08                        # 4 gambar x $0,02
    n = len([r for r in fake.requests if r.url.path.endswith("/images") and r.method == "POST"])
    r = api.raw.post(f"/api/characters/{ch['id']}/sheet", json={"model": M})
    assert r.status_code == 409                       # tanpa konfirmasi tidak ada panggilan berbayar
    assert len([x for x in fake.requests if x.url.path.endswith("/images") and x.method == "POST"]) == n
    r = api.raw.post(f"/api/characters/{ch['id']}/sheet", json={"model": M, "confirmed_cost": est["high"]})
    assert r.status_code == 200, r.text
    labels = [i["label"] for i in r.json()["images"]]
    assert labels == ["source", "front", "side", "three_quarter", "full_body"]
    prompts = [__import__("json").loads(x.content)["prompt"] for x in fake.requests
               if x.url.path.endswith("/images") and x.method == "POST"][-4:]
    assert all("red jacket" in p and "identical" in p for p in prompts)
    imgs = {i["id"]: i for i in api.get("/api/images").json()}
    assert sum(1 for i in imgs.values() if i["kind"] == "sheet") == 4
    assert api.studio.db.committed_today() >= 0.04     # biaya (0,01 per gambar dari provider palsu) tercatat


def test_sheet_total_respects_per_job_limit(api, settings):
    src, ch = make_char(api)
    api.studio.s = type(settings)(**{**settings.__dict__, "max_cost_per_job": 0.05})
    r = api.raw.post(f"/api/characters/{ch['id']}/sheet", json={"model": M, "confirmed_cost": 0.08})
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
    assert db.one("PRAGMA user_version")["user_version"] == 4
