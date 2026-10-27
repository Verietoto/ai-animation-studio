from conftest import upload
from test_delete import VIDEO, clip_file, make_clip
from test_workspaces import hdr, mkws, up


def bulk(api, ws=None, **ids):
    body = {"image_ids": [], "clip_ids": [], "character_ids": [], **ids}
    return api.post("/api/bulk-delete", json=body, **(hdr(ws) if ws else {}))


def extend(api, parent):
    child = api.post(f"/api/clips/{parent}/extend", json={"prompt": "lanjut", "model": VIDEO["model"]}).json()["id"]
    api.studio.poll_once()
    return child


def test_whole_extend_chain_is_deleted_regardless_of_order(api):
    a = make_clip(api)
    b = extend(api, a)
    c = extend(api, b)
    files = [clip_file(api, x) for x in (a, b, c)]
    r = bulk(api, clip_ids=[a, b, c])   # induk dulu: server yang mengurutkan dari yang terdalam
    assert r.json() == {"deleted": {"images": 0, "clips": 3, "characters": 0}, "skipped": 0, "failed": []}
    assert api.get("/api/clips").json() == [] and not any(f.exists() for f in files)


def test_parent_without_selected_child_fails_with_reason_others_still_deleted(api):
    parent = make_clip(api)
    extend(api, parent)
    other = make_clip(api)
    r = bulk(api, clip_ids=[parent, other]).json()
    assert r["deleted"]["clips"] == 1
    assert [f["id"] for f in r["failed"]] == [parent] and "lanjutan" in r["failed"][0]["reason"]


def test_running_clip_is_refused(api):
    running = make_clip(api, complete=False)
    r = bulk(api, clip_ids=[running]).json()
    assert r["deleted"]["clips"] == 0 and r["failed"][0]["type"] == "clip"


def test_character_and_its_image_in_one_request(api):
    img = upload(api)["id"]
    char = api.post("/api/characters", json={"name": "Rina", "description": "bob", "source_image_id": img}).json()["id"]
    assert bulk(api, image_ids=[img]).json()["failed"][0]["type"] == "image"   # tanpa karakter: ditolak
    r = bulk(api, image_ids=[img], character_ids=[char]).json()
    assert r["deleted"] == {"images": 1, "clips": 0, "characters": 1} and r["failed"] == []


def test_repeat_request_counts_as_skipped_and_duplicates_are_dropped(api):
    img = upload(api)["id"]
    assert bulk(api, image_ids=[img, img]).json()["deleted"]["images"] == 1
    r = bulk(api, image_ids=[img]).json()
    assert r == {"deleted": {"images": 0, "clips": 0, "characters": 0}, "skipped": 1, "failed": []}


def test_empty_list_is_400_and_cap_is_200(api):
    assert bulk(api).status_code == 400
    assert bulk(api, image_ids=[f"x{i}" for i in range(201)]).status_code == 422
    assert bulk(api, image_ids=[f"x{i}" for i in range(200)]).json()["skipped"] == 200


def test_other_workspace_ids_are_skipped_and_untouched(api):
    other = mkws(api, "lain")
    mine_img, mine_clip = up(api), make_clip(api)   # milik "main"
    theirs = up(api, other)
    r = bulk(api, other, image_ids=[mine_img], clip_ids=[mine_clip]).json()   # dikirim dari workspace lain
    assert r["skipped"] == 2 and r["deleted"] == {"images": 0, "clips": 0, "characters": 0}
    assert [c["id"] for c in api.get("/api/clips").json()] == [mine_clip]
    assert mine_img in [i["id"] for i in api.get("/api/images").json()]
    assert bulk(api, other, image_ids=[theirs]).json()["deleted"]["images"] == 1
