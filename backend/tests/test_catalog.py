import json
from pathlib import Path

import pytest

from app import pricing
from app.service import ServiceError

FIX = Path(__file__).parent / "fixtures"
MODELS = {m["id"]: m for m in json.loads((FIX / "video_models.json").read_text())["data"]}


def card(model):
    return pricing.video_price_card(MODELS[model])


def per_second(model, res, audio=None):
    rows = [r for r in card(model)["rows"] if r["label"] == res and r["audio"] in (audio, None)]
    assert rows, (model, res, card(model)["rows"])
    return rows[0]


def test_every_fixture_video_model_has_a_card():
    assert len(MODELS) == 30
    for m in MODELS.values():
        c = pricing.video_price_card(m)
        assert c["rows"] and c["example"]["confidence"] in {"exact", "formula", "unknown"}
        assert c["selectable"] == (c["category"] == "i2v")
        assert (c["disabled_reason"] is None) == c["selectable"]


@pytest.mark.parametrize("model,res,audio,expected", [
    ("x-ai/grok-imagine-video-1.5-lite", "480p", None, 0.02),   # sen per detik
    ("alibaba/wan-3.0", "480p", None, 0.05),                     # USD per detik
    ("kwaivgi/kling-v3.0-pro", "720p", False, 0.112),            # i2v tanpa suara
    ("kwaivgi/kling-v3.0-pro", "720p", True, 0.168),             # i2v dengan suara
    ("google/veo-3.1-fast", "720p", False, 0.08),
])
def test_per_second_rows_hand_computed(model, res, audio, expected):
    row = per_second(model, res, audio)
    assert row["confidence"] == "exact"
    assert row["usd_per_second"] == pytest.approx(expected, rel=1e-6)


def test_token_priced_model_is_formula_not_exact():
    rows = card("bytedance/seedance-2.5")["rows"]
    assert rows and all(r["confidence"] == "formula" for r in rows)


def test_aleph_minimum_is_a_note_not_a_per_second_rate():
    c = card("runway/aleph-2")
    assert c["category"] == "edit" and not c["selectable"] and "video" in c["disabled_reason"].lower()
    assert c["rows"][0]["usd_per_second"] == pytest.approx(0.28)   # bukan 0,56 (minimum per job)
    assert any("minimum $0.56" in n for n in c["notes"])
    assert c["example"]["low"] == pytest.approx(1.40)               # 5 detik x 0,28 > minimum


def test_non_i2v_categories_are_labelled_and_disabled():
    cats = {mid: pricing.video_category(m) for mid, m in MODELS.items()}
    assert cats["black-forest-labs/flux-video-upscale"] == "upscale"
    assert cats["heygen/avatar-iv"] == "avatar"
    assert cats["black-forest-labs/flux-video-edit"] == "edit"
    assert pricing.video_price_card(MODELS["black-forest-labs/flux-video-upscale"])["rows"][0]["confidence"] == "unknown"


def test_video_catalog_endpoint_matches_estimate(api):
    models = api.get("/api/catalog/video").json()["models"]
    assert models
    checked = 0
    for m in models:
        ex = m["price"]["example"]
        if not m["price"]["selectable"] or ex["confidence"] == "unknown":
            continue
        caps = m["capabilities"]
        body = {"kind": "video", "model": m["id"], "generate_audio": False,
                "duration": 5 if 5 in (caps["durations"] or [5]) else min(caps["durations"])}
        if caps["resolutions"]:
            body["resolution"] = caps["resolutions"][0]
        est = api.post("/api/estimate", json=body).json()
        assert est["high"] == pytest.approx(ex["high"], rel=1e-6), m["id"]
        checked += 1
    assert checked >= 1


def test_image_catalog_lists_text_only_models_disabled(api):
    models = {m["id"]: m for m in api.get("/api/catalog/image").json()["models"]}
    assert models["openai/gpt-image-2"]["price"]["selectable"]
    text_only = models["x/text-only"]["price"]
    assert not text_only["selectable"] and "teks" in text_only["disabled_reason"].lower()
    # model teks-saja tetap tidak bisa dipakai edit walau tampil di katalog
    r = api.raw.post("/api/images/nope/edit", json={"prompt": "x", "model": "x/text-only", "reference_image_ids": []})
    assert r.status_code in (400, 404, 422)


def test_image_card_matches_estimate_and_survives_one_endpoint_failure(api):
    ok = {m["id"]: m for m in api.get("/api/catalog/image").json()["models"]}["openai/gpt-image-2"]["price"]["example"]
    est = api.post("/api/estimate", json={"kind": "image_edit", "model": "openai/gpt-image-2", "reference_count": 0}).json()
    assert est["high"] == pytest.approx(ok["high"], rel=1e-6)

    studio = api.studio
    real = studio._image_endpoints

    def flaky(model):
        if model == "x/text-only":
            raise ServiceError("provider mati", 502)
        return real(model)
    studio._image_endpoints = flaky
    models = {m["id"]: m for m in api.get("/api/catalog/image?refresh=1").json()["models"]}
    assert models["x/text-only"]["price"]["example"]["confidence"] == "unknown"
    assert "provider mati" in models["x/text-only"]["price"]["notes"][0]
    assert models["openai/gpt-image-2"]["price"]["example"]["confidence"] != "unknown"
