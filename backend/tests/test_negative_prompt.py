from conftest import upload

KLING = {"model": "kwaivgi/kling-v3.0-std", "prompt": "adegan", "duration": 5}
VEO = {"model": "google/veo-3.1-lite", "prompt": "adegan", "duration": 4}


def test_atlas_cloud_gets_flat_snake_case_option(api, fake):
    r = api.post("/api/clips", json={**KLING, "image_id": upload(api)["id"], "negative_prompt": " teks, watermark "})
    assert r.status_code == 200, r.text
    sent = fake.last_json("/videos")
    assert sent["provider"] == {"options": {"atlas-cloud": {"negative_prompt": "teks, watermark"}}}
    assert "negative_prompt" not in sent   # bukan field payload tingkat atas
    assert r.json()["negative_prompt"] == "teks, watermark"


def test_google_vertex_gets_parameters_wrapper_and_camel_case(api, fake):
    api.post("/api/clips", json={**VEO, "image_id": upload(api)["id"], "negative_prompt": "blur"})
    assert fake.last_json("/videos")["provider"] == {"options": {"google-vertex": {"parameters": {"negativePrompt": "blur"}}}}


def test_unsupported_model_is_refused_before_submit(api, fake):
    r = api.post("/api/clips", json={"model": "bytedance/seedance-2.5", "prompt": "x", "duration": 4,
                                     "image_id": upload(api)["id"], "negative_prompt": "blur"})
    assert r.status_code == 400 and "negative prompt" in r.json()["detail"]
    assert fake.submit_count == 0


def test_blank_negative_prompt_is_ignored_even_for_unsupported_model(api, fake):
    r = api.post("/api/clips", json={"model": "bytedance/seedance-2.5", "prompt": "x", "duration": 4,
                                     "image_id": upload(api)["id"], "negative_prompt": "   "})
    assert r.status_code == 200 and "provider" not in fake.last_json("/videos")
    assert r.json()["negative_prompt"] is None


def test_extend_passes_negative_prompt(api, fake):
    clip = api.post("/api/clips", json={**KLING, "image_id": upload(api)["id"]}).json()
    api.studio.poll_once()
    r = api.post(f"/api/clips/{clip['id']}/extend", json={"prompt": "lanjut", "model": KLING["model"], "duration": 5,
                                                          "negative_prompt": "tangan cacat"})
    assert r.status_code == 200, r.text
    assert fake.last_json("/videos")["provider"]["options"]["atlas-cloud"] == {"negative_prompt": "tangan cacat"}


def test_catalog_exposes_parameter_name(api):
    caps = {m["id"]: m["capabilities"]["negative_prompt"] for m in api.get("/api/catalog/video").json()["models"]}
    assert caps["kwaivgi/kling-v3.0-std"] == "negative_prompt"
    assert caps["google/veo-3.1-lite"] == "negativePrompt"
    assert caps["bytedance/seedance-2.5"] is None


def test_too_long_is_422(api):
    r = api.post("/api/clips", json={**KLING, "image_id": upload(api)["id"], "negative_prompt": "x" * 2001})
    assert r.status_code == 422
