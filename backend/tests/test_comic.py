"""Plan 21: panel komik (CRUD, balon, prompt tanpa teks dialog, generate dengan konfirmasi biaya, take). OpenRouter palsu."""
from app import comic_prompt
from test_workspaces import char, mkws, up

IMG = "openai/gpt-image-2"   # katalog palsu: rasio 1:1/16:9, maks 3 gambar referensi


def panel(api, **patch):
    p = api.post("/api/comic-panels", json={}).json()
    if patch:
        r = api.raw.put(f"/api/comic-panels/{p['id']}", json=patch)
        assert r.status_code == 200, r.text
        p = r.json()
    return p


def bubble(**kw):
    return {"id": "b1", "kind": "speech", "text": "Halo!", "x": 0.1, "y": 0.05, "w": 0.3, "h": 0.15, **kw}


def est(api, pid, model=IMG):
    return api.raw.post("/api/estimate", json={"kind": "comic_panel", "model": model, "panel_id": pid})


def test_crud_defaults_and_validation(api):
    p = panel(api)
    assert (p["title"], p["shot"], p["angle"], p["aspect_ratio"], p["comic_style"], p["takes"]) == ("Panel 1", "MS", "eye", "4:3", "project", [])
    pid = p["id"]
    bad = [{"shot": "XX"}, {"angle": "miring"}, {"comic_style": "pop"}, {"aspect_ratio": "5:4"}, {"title": " "},
           {"character_ids": ["tidak-ada"]}, {"location_id": "tidak-ada"}, {"bubbles": [bubble(kind="teriak")]},
           {"bubbles": [bubble(text=" ")]}, {"bubbles": [bubble(x=0.9, w=0.3)]}, {"bubbles": [bubble(), bubble()]},
           {"bubbles": [bubble(w=0)]}, {"image_id": "lain"}, {"title": None}, {"salah": 1}]
    for patch in bad:
        assert api.raw.put(f"/api/comic-panels/{pid}", json=patch).status_code in (404, 422), patch
    got = api.raw.put(f"/api/comic-panels/{pid}", json={"title": "Pembuka", "shot": "CU", "bubbles": [bubble(), bubble(id="b2", kind="sfx", text="BRAK")]}).json()
    assert got["title"] == "Pembuka" and got["shot"] == "CU" and [b["kind"] for b in got["bubbles"]] == ["speech", "sfx"]
    assert [x["id"] for x in api.get("/api/comic-panels").json()] == [pid]
    assert api.raw.delete(f"/api/comic-panels/{pid}").json() == {"ok": True}
    assert api.raw.get(f"/api/comic-panels/{pid}").status_code == 404


def test_panels_are_per_project(api):
    pid = panel(api)["id"]
    ws = mkws(api, "Lain")
    assert api.get("/api/comic-panels", headers={"X-Workspace-Id": ws}).json() == []
    assert api.raw.get(f"/api/comic-panels/{pid}", headers={"X-Workspace-Id": ws}).status_code == 404


def test_prompt_never_contains_bubble_text_and_numbers_images():
    p = {"comic_style": "manga", "shot": "CU", "angle": "low", "description": "Momon terkejut melihat kue"}
    text = comic_prompt.build(p, [{"name": "Momon", "description": "kucing oranye", "image_id": "a"}, {"name": "Sari", "description": "", "image_id": None}],
                              {"name": "Dapur", "description": "hangat", "image_id": "l"}, "kartun 2D")
    assert "manga" in text and "close-up" in text and "low angle" in text and "Visual style: kartun 2D." in text
    assert "Image 1 is the LOCATION Dapur" in text and "Image 2 shows CHARACTER Momon" in text and "CHARACTER Sari." in text
    assert "No text, no lettering, no speech bubbles" in text


def test_generate_requires_confirmation_sends_references_and_new_take_becomes_active(api, fake):
    cid, cimg = char(api, name="Momon")
    loc = api.post("/api/locations", json={"name": "Dapur", "description": "hangat", "image_id": up(api)}).json()
    p = panel(api, character_ids=[cid], location_id=loc["id"], description="Momon mencium kue",
              bubbles=[bubble(text="Wangi sekali!", character_id=cid)])
    pv = api.get(f"/api/comic-panels/{p['id']}/preview", params={"model": IMG}).json()
    assert pv["inputs"] == [loc["image_id"], cimg] and any("4:3" in w for w in pv["warnings"])   # model palsu tidak punya 4:3
    e = est(api, p["id"]).json()
    gen = f"/api/comic-panels/{p['id']}/generate"
    assert api.raw.post(gen, json={"model": IMG}).status_code == 409
    first = api.raw.post(gen, json={"model": IMG, "confirmed_cost": e["high"]}).json()
    body = fake.last_json("/images")
    assert len(body["input_references"]) == 2 and "Wangi sekali" not in body["prompt"] and "Momon mencium kue" in body["prompt"]
    second = api.raw.post(gen, json={"model": IMG, "confirmed_cost": e["high"]}).json()
    assert len(second["takes"]) == 2 and second["image_id"] == second["takes"][-1] != first["image_id"]
    back = api.raw.put(f"/api/comic-panels/{p['id']}", json={"image_id": first["image_id"]}).json()
    assert back["image_id"] == first["image_id"]
    assert api.studio.db.one("SELECT kind FROM images WHERE id = ?", (first["image_id"],))["kind"] == "comic_panel"


def test_without_images_uses_text_to_image_and_too_many_refs_is_refused(api, fake):
    p = panel(api, aspect_ratio="16:9", description="Langit malam")
    e = est(api, p["id"]).json()
    r = api.raw.post(f"/api/comic-panels/{p['id']}/generate", json={"model": IMG, "confirmed_cost": e["high"]})
    assert r.status_code == 200, r.text
    body = fake.last_json("/images")
    assert "input_references" not in body and body["aspect_ratio"] == "16:9"
    ids = [char(api, name=n)[0] for n in ("A", "B", "C", "D")]                  # 4 karakter > maks 3 gambar model palsu
    q = panel(api, character_ids=ids)
    assert est(api, q["id"]).status_code in (400, 422)


def test_deleted_character_location_and_take_are_cleaned_on_read(api, fake):
    cid, _ = char(api, name="Momon")
    loc = api.post("/api/locations", json={"name": "Dapur"}).json()["id"]
    p = panel(api, character_ids=[cid], location_id=loc)
    e = est(api, p["id"]).json()
    made = api.raw.post(f"/api/comic-panels/{p['id']}/generate", json={"model": IMG, "confirmed_cost": e["high"]}).json()
    assert api.raw.delete(f"/api/characters/{cid}").status_code in (200, 204)
    assert api.raw.delete(f"/api/locations/{loc}").status_code in (200, 204)
    assert api.raw.delete(f"/api/images/{made['image_id']}").status_code in (200, 204)
    got = api.get(f"/api/comic-panels/{p['id']}").json()
    assert (got["character_ids"], got["location_id"], got["image_id"], got["takes"]) == ([], None, None, [])


def test_deleting_project_removes_its_panels(api):
    ws = mkws(api, "Komik")
    api.post("/api/comic-panels", json={}, headers={"X-Workspace-Id": ws})
    assert api.studio.db.one("SELECT COUNT(*) AS n FROM comic_panels WHERE workspace_id = ?", (ws,))["n"] == 1
    api.studio.workspaces.archive(ws, "main")
    api.studio.workspaces.delete(ws, "main")
    assert api.studio.db.one("SELECT COUNT(*) AS n FROM comic_panels WHERE workspace_id = ?", (ws,))["n"] == 0
