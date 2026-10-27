import pytest

from app import sceneprompt
from test_scene_generate import estimate
from test_workspaces import hdr, mkws

MODEL = "openai/gpt-image-2"      # tiruan: rasio 1:1 / 16:9 / auto, tanpa 3:4
DESC = "Gadis desa 17 tahun, rambut dikepang, kebaya merah, gaya anime"


def portrait(api, desc=DESC, model=MODEL, ws=None, **kw):
    est = estimate(api, kind="character_portrait", model=model, description=desc) if desc.strip() else {"high": 0}
    return api.raw.post("/api/characters/portrait", json={"description": desc, "model": model, "confirmed_cost": est["high"], **kw},
                        **(hdr(ws) if ws else {}))


def posts_to_images(fake):
    return [x for x in fake.requests if x.url.path.endswith("/images") and x.method == "POST"]


def test_prompt_uses_description_only_and_asks_for_a_clean_portrait():
    p = sceneprompt.portrait_prompt("rambut bob " + "x" * 2000)
    assert "rambut bob" in p and "plain light grey studio background" in p and "No text" in p
    assert len(p) < 1100                                                               # deskripsi dipotong 800 karakter


def test_creates_one_portrait_image_with_cost_and_kind(api, fake):
    before = api.studio.db.committed_today()
    r = portrait(api)
    assert r.status_code == 200, r.text
    img = r.json()
    assert img["kind"] == "portrait" and img["parent_image_id"] is None and "kebaya merah" in img["prompt"]
    sent = fake.last_json("/images")
    assert sent["model"] == MODEL and "input_references" not in sent                     # teks ke gambar murni, tanpa nama
    assert api.studio.db.committed_today() == pytest.approx(before + 0.01)
    assert api.get(f"/api/images/{img['id']}/file").status_code == 200
    assert [i["id"] for i in api.get("/api/images").json()] == [img["id"]]
    assert api.get("/api/characters").json() == []                                       # tidak membuat karakter


def test_portrait_becomes_a_character_through_the_existing_endpoint(api):
    img = portrait(api).json()
    r = api.post("/api/characters", json={"name": "Rani", "description": DESC, "source_image_id": img["id"]})
    assert r.status_code == 200 and r.json()["source_image_id"] == img["id"]


def test_requires_cost_confirmation(api, fake):
    r = api.raw.post("/api/characters/portrait", json={"description": DESC, "model": MODEL})
    assert r.status_code == 409
    assert not posts_to_images(fake)


def test_blank_or_too_long_description_is_refused_before_cost(api, fake):
    assert api.raw.post("/api/estimate", json={"kind": "character_portrait", "model": MODEL, "description": "   "}).status_code == 422
    assert api.raw.post("/api/estimate", json={"kind": "character_portrait", "model": MODEL}).status_code == 422
    r = api.raw.post("/api/characters/portrait", json={"description": "x" * 2001, "model": MODEL, "confirmed_cost": 1})
    assert r.status_code == 422
    assert not posts_to_images(fake)


def test_unknown_model_is_refused_before_cost(api, fake):
    r = api.raw.post("/api/characters/portrait", json={"description": DESC, "model": "x/text-only", "confirmed_cost": 1})
    assert r.status_code == 400 and "tidak dikenal" in r.json()["detail"]
    assert not posts_to_images(fake)


def test_provider_error_leaves_no_image_and_no_cost(api, fake):
    est = estimate(api, kind="character_portrait", model=MODEL, description=DESC)
    fake.image_error = "Seedream blocked this request through content moderation."
    before = api.studio.db.committed_today()
    r = api.raw.post("/api/characters/portrait", json={"description": DESC, "model": MODEL, "confirmed_cost": est["high"]})
    assert r.status_code == 502 and "moderation" in r.json()["detail"]
    assert api.get("/api/images").json() == [] and api.studio.db.committed_today() == before


def test_empty_model_answer_is_422_without_image(api, fake):
    est = estimate(api, kind="character_portrait", model=MODEL, description=DESC)
    fake.edit_returns_image = False
    r = api.raw.post("/api/characters/portrait", json={"description": DESC, "model": MODEL, "confirmed_cost": est["high"]})
    assert r.status_code == 422 and api.get("/api/images").json() == []


def test_daily_budget_blocks_portrait(api, fake):
    est = estimate(api, kind="character_portrait", model=MODEL, description=DESC)
    api.studio.s = type(api.studio.s)(**{**api.studio.s.__dict__, "daily_budget_usd": 0.0001})
    r = api.raw.post("/api/characters/portrait", json={"description": DESC, "model": MODEL, "confirmed_cost": est["high"]})
    assert r.status_code == 402
    assert not posts_to_images(fake)


def test_portrait_is_stored_in_the_requesting_workspace(api):
    ws = mkws(api, "lain")
    img = portrait(api, ws=ws).json()
    assert [i["id"] for i in api.get("/api/images", **hdr(ws)).json()] == [img["id"]]
    assert api.get("/api/images").json() == []


def test_aspect_ratio_3_4_is_sent_only_when_the_model_supports_it(api, monkeypatch):
    assert api.studio.portrait_plan(MODEL, DESC)["options"] == {}
    info = {"id": "x/portrait-ok", "supported_parameters": {"aspect_ratio": {"type": "enum", "values": ["1:1", "3:4"]}}}
    monkeypatch.setattr(api.studio, "image_models", lambda: [info])
    assert api.studio.portrait_plan("x/portrait-ok", DESC)["options"] == {"aspect_ratio": "3:4"}
