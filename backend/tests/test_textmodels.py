import json

import pytest

from app import textai
from app.openrouter import OpenRouterError
from app.service import ServiceError
from test_journey import split_setup
from test_scene_generate import estimate, ready_scene

HAIKU = "anthropic/claude-haiku-5.5"


def chat_bodies(fake):
    return [json.loads(r.content) for r in fake.requests if r.url.path.endswith("/chat/completions")]


def blockout(api, s, model=None, **kw):
    est = estimate(api, kind="scene_blockout", model=model or "-", scene_id=s)
    return api.raw.post(f"/api/scenes/{s}/blockout", json={"confirmed_cost": est["high"], **({"model": model} if model else {}), **kw})


LAYOUT = lambda cid: {"version": 1, "duration": 5, "camera": {"keys": [{"t": 0, "pos": [0, 1.6, 6], "target": [0, 1.2, 0], "mm": 35}]},
                      "actors": [{"character_id": cid, "keys": [{"t": 0, "pos": [0, 0, 0], "facing": 0, "pose": "stand"}]}], "props": []}


# ---------- katalog ----------
def test_catalog_keeps_only_usable_models_and_marks_capabilities(api):
    body = api.get("/api/models/text").json()
    ids = [m["id"] for m in body["models"]]
    assert body["default"] == HAIKU
    assert set(ids) == {HAIKU, "x/cheap-json", "x/pricey"}          # tanpa harga negatif, konteks kecil, tanpa JSON, keluaran gambar, :free
    by = {m["id"]: m for m in body["models"]}
    assert by[HAIKU]["structured"] and by[HAIKU]["reasoning"] and by[HAIKU]["vision"] and not by[HAIKU]["expensive"]
    assert by[HAIKU]["prompt_per_m"] == pytest.approx(0.1) and by[HAIKU]["completion_per_m"] == pytest.approx(0.5)
    assert not by["x/cheap-json"]["structured"] and not by["x/cheap-json"]["reasoning"] and not by["x/cheap-json"]["vision"]
    assert by["x/pricey"]["expensive"] and ids[-1] == "x/pricey"                                     # mahal diurutkan paling bawah


def test_catalog_is_cached_between_calls(api, fake):
    api.get("/api/models/text")
    api.get("/api/models/text")
    estimate(api, kind="scene_blockout", model="-", scene_id=ready_scene(api)[1])
    assert len([r for r in fake.requests if r.url.path == "/api/v1/models"]) == 1


# ---------- model per permintaan ----------
def test_selected_model_is_used_for_estimate_cost_and_record(api, fake):
    _, s, (cid,) = ready_scene(api)
    fake.chat_content = json.dumps(LAYOUT(cid))
    default = estimate(api, kind="scene_blockout", model="-", scene_id=s)
    cheap = estimate(api, kind="scene_blockout", model="x/cheap-json", scene_id=s)
    assert cheap["high"] < default["high"] and "x/cheap-json" in cheap["basis"][0]
    r = blockout(api, s, "x/cheap-json")
    assert r.status_code == 200, r.text
    sent = chat_bodies(fake)[-1]
    assert sent["model"] == "x/cheap-json" and sent["response_format"] == {"type": "json_object"} and "reasoning" not in sent
    assert api.studio.db.one("SELECT model FROM text_jobs ORDER BY created_at DESC")["model"] == "x/cheap-json"


def test_default_model_gets_low_reasoning_and_placeholder_means_default(api, fake):
    _, s, (cid,) = ready_scene(api)
    fake.chat_content = json.dumps(LAYOUT(cid))
    assert blockout(api, s).status_code == 200                      # tanpa `model`
    sent = chat_bodies(fake)[-1]
    assert sent["model"] == HAIKU and sent["reasoning"] == {"effort": "low"}
    est = estimate(api, kind="scene_blockout", model="teks", scene_id=s)        # nilai lama dari klien = bawaan
    assert HAIKU in est["basis"][0]


@pytest.mark.parametrize("bad", ["x/router-auto", "x/tiny-context", "x/no-json", "x/image-maker", "x/free:free", "tidak/ada"])
def test_unusable_model_is_refused_before_any_cost(api, fake, bad):
    _, s, _ = ready_scene(api)
    r = api.raw.post("/api/estimate", json={"kind": "scene_blockout", "model": bad, "scene_id": s})
    assert r.status_code == 422 and "model teks tidak tersedia" in r.json()["detail"]
    r = api.raw.post(f"/api/scenes/{s}/blockout", json={"model": bad, "confirmed_cost": 1})
    assert r.status_code == 422
    assert not chat_bodies(fake)


def test_expensive_model_is_listed_but_per_job_limit_still_protects(api, fake):
    f, a, b, l1 = split_setup(api)
    est = api.raw.post("/api/estimate", json={"kind": "episode_split", "model": "x/pricey", "film_id": f}).json()
    assert est["high"] > 1.0                                                                   # 12.000 token × $100/M
    r = api.raw.post(f"/api/films/{f}/split", json={"model": "x/pricey", "confirmed_cost": est["high"]})
    assert r.status_code == 402 and not chat_bodies(fake)


def test_split_accepts_a_model_too(api, fake):
    f, a, b, l1 = split_setup(api)
    fake.chat_content = json.dumps({"scenes": [{"location_id": l1, "cast": [{"character_id": a, "action": "x"}]}]})
    est = api.raw.post("/api/estimate", json={"kind": "episode_split", "model": "x/cheap-json", "film_id": f}).json()
    assert api.raw.post(f"/api/films/{f}/split", json={"model": "x/cheap-json", "confirmed_cost": est["high"]}).status_code == 200
    assert chat_bodies(fake)[-1]["model"] == "x/cheap-json"


# ---------- skema ketat dan cadangan ----------
SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"], "additionalProperties": False}


def ask(api, model, schema=SCHEMA):
    est = textai.estimate(api.studio, "s", "u", 100, model=model)
    with api.studio._lock:
        return textai.ask(api.studio, "uji", "s", "u", 100, est, "main", est.high, False, model=model, schema=schema)


def test_strict_schema_is_sent_only_to_models_that_support_it(api, fake):
    fake.chat_content = '{"a": 1}'
    assert ask(api, HAIKU)[0] == {"a": 1}
    sent = chat_bodies(fake)[-1]
    assert sent["response_format"]["type"] == "json_schema" and sent["response_format"]["json_schema"]["strict"] is True
    assert sent["response_format"]["json_schema"]["schema"] == SCHEMA and sent["provider"] == {"require_parameters": True}
    ask(api, "x/cheap-json")
    sent = chat_bodies(fake)[-1]
    assert sent["response_format"] == {"type": "json_object"} and "provider" not in sent


def test_schema_rejected_by_provider_is_retried_once_with_json_object(api, fake):
    fake.chat_content, fake.chat_reject_schema = '{"a": 2}', True
    assert ask(api, HAIKU)[0] == {"a": 2}
    kinds = [b["response_format"]["type"] for b in chat_bodies(fake)]
    assert kinds == ["json_schema", "json_object"]
    assert api.studio.db.one("SELECT COUNT(*) AS n FROM text_jobs")["n"] == 1                   # satu pekerjaan berbiaya


# ---------- jawaban bermasalah ----------
def test_empty_answer_from_exhausted_tokens_has_a_specific_message_and_cost_is_kept(api, fake):
    _, s, _ = ready_scene(api)
    fake.chat_content, fake.chat_finish = "", "length"
    before = api.studio.db.committed_today()
    r = blockout(api, s)
    assert r.status_code == 502 and "kehabisan token" in r.json()["detail"]
    assert api.studio.db.committed_today() > before


def test_parse_json_tolerates_preface_fences_and_braces_in_strings():
    assert textai.parse_json('Berikut JSON-nya: {"a": {"b": "}{"}, "c": 1} semoga membantu') == {"a": {"b": "}{"}, "c": 1}
    assert textai.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert textai.parse_json('{"a": "kutip \\" dan } di string"}')["a"].startswith("kutip")
    with pytest.raises(ValueError):
        textai.parse_json("tidak ada json")
    with pytest.raises(ValueError):
        textai.parse_json('{"a": 1')                    # tidak lengkap
    with pytest.raises(ValueError):
        textai.parse_json("[1, 2]")                      # bukan objek


def test_catalog_failure_is_a_clear_502(api, monkeypatch):
    def boom():
        raise OpenRouterError("mati", 500)
    monkeypatch.setattr(api.studio.client, "list_models", boom)
    api.studio._text_catalog = None
    with pytest.raises(ServiceError) as exc:
        textai.catalog(api.studio)
    assert exc.value.status == 502
