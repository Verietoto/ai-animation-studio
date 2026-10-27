import json

from app.db import Database
from test_workspace_delete import archive, populate
from test_workspaces import char, clip, hdr, mkws, up


def film(api, ws=None, title="Ep"):
    return api.post("/api/films", json={"title": title}, **(hdr(ws) if ws else {})).json()["id"]


def scene(api, film_id, ws=None, **body):
    r = api.post(f"/api/films/{film_id}/scenes", json=body, **(hdr(ws) if ws else {}))
    assert r.status_code == 200, r.text
    return r.json()


def put(api, scene_id, ws=None, **body):
    return api.put(f"/api/scenes/{scene_id}", json=body, **(hdr(ws) if ws else {}))


def numbers(api, film_id):
    return [(s["number"], s["id"]) for s in api.get(f"/api/films/{film_id}").json()["scenes"]]


# ---------- episode ----------
def test_episode_numbers_and_fields(api):
    a, b = film(api, title="Satu"), film(api, title="Dua")
    eps = api.get("/api/films").json()
    assert [(e["number"], e["title"]) for e in eps] == [(1, "Satu"), (2, "Dua")]
    got = api.put(f"/api/films/{b}", json={"number": 5, "synopsis": "Pulang ke desa", "aspect_ratio": "9:16"}).json()
    assert (got["number"], got["synopsis"], got["aspect_ratio"]) == (5, "Pulang ke desa", "9:16")
    assert api.put(f"/api/films/{b}", json={"aspect_ratio": "lebar"}).status_code == 422
    assert api.put(f"/api/films/{b}", json={"number": 0}).status_code == 422
    assert api.get(f"/api/films/{a}").json()["aspect_ratio"] == "16:9"


# ---------- adegan: tambah, warisan, urut, hapus, duplikat ----------
def test_scene_add_inherits_location_time_and_cast_but_not_action(api):
    f, (cid, _) = film(api), char(api)
    loc = api.post("/api/locations", json={"name": "Sawah"}).json()["id"]
    outfit = api.post(f"/api/characters/{cid}/outfits", json={"name": "Kebaya", "description": "kebaya merah"}).json()["id"]
    first = scene(api, f)
    assert first["status"] == "naskah" and first["cast"] == [] and first["location"] is None
    put(api, first["id"], location_id=loc, time_of_day="senja", camera="dolly in",
        cast=[{"character_id": cid, "outfit_id": outfit, "action": "berlari"}])
    second = scene(api, f)
    assert second["location"]["name"] == "Sawah" and second["time_of_day"] == "senja"
    assert second["camera"] == ""                                   # kamera tidak diwarisi
    assert [(c["character_id"], c["outfit_id"], c["action"]) for c in second["cast"]] == [(cid, outfit, "")]
    assert scene(api, f, inherit=False)["cast"] == []


def test_scene_order_insert_after_delete_and_duplicate(api):
    f = film(api)
    a, b = scene(api, f)["id"], scene(api, f)["id"]
    mid = scene(api, f, after_scene_id=a)["id"]
    assert [i for _, i in numbers(api, f)] == [a, mid, b] and [n for n, _ in numbers(api, f)] == [1, 2, 3]
    put(api, mid, dialogue="halo", camera="pan")
    dup = api.post(f"/api/scenes/{mid}/duplicate").json()
    assert dup["dialogue"] == "halo" and dup["camera"] == "pan" and dup["clip_id"] is None
    assert [i for _, i in numbers(api, f)] == [a, mid, dup["id"], b]
    assert api.put(f"/api/films/{f}/scene-order", json={"scene_ids": [b, dup["id"], mid, a]}).status_code == 200
    assert [i for _, i in numbers(api, f)] == [b, dup["id"], mid, a]
    assert api.put(f"/api/films/{f}/scene-order", json={"scene_ids": [a, b]}).status_code == 409      # himpunan harus sama
    assert api.put(f"/api/films/{f}/scene-order", json={"scene_ids": [a, a, b, mid]}).status_code == 409
    assert api.delete(f"/api/scenes/{b}").status_code == 200
    assert [n for n, _ in numbers(api, f)] == [1, 2, 3]            # nomor dirapatkan ulang


def test_scene_limits_and_validation(api):
    f = film(api)
    c1, c2, c3, c4 = (char(api, name=n)[0] for n in "ABCD")
    s = scene(api, f)["id"]

    def cast(*ids):
        return [{"character_id": i} for i in ids]

    assert put(api, s, cast=cast(c1, c2, c3)).status_code == 200
    assert put(api, s, cast=cast(c1, c2, c3, c4)).status_code == 422          # maksimal 3 pemeran
    assert put(api, s, cast=cast(c1, c1)).status_code == 422                   # karakter sama dua kali
    assert put(api, s, cast=[{"character_id": c1, "outfit_id": "x"}]).status_code == 422
    assert put(api, s, camera="x" * 121).status_code == 422
    assert put(api, s, cast=[{"character_id": c1, "action": "y" * 201}]).status_code == 422
    assert put(api, s, bogus="x").status_code == 422
    assert [c["character_id"] for c in api.get(f"/api/films/{f}").json()["scenes"][0]["cast"]] == [c1, c2, c3]   # gagal = tidak berubah
    other = api.post(f"/api/characters/{c1}/outfits", json={"name": "Jas", "description": "jas"}).json()["id"]
    assert put(api, s, cast=[{"character_id": c2, "outfit_id": other}]).status_code == 422   # tampilan milik karakter lain


def test_partial_update_keeps_other_fields(api):
    s = scene(api, film(api))["id"]
    put(api, s, camera="orbit", dialogue="a")
    got = put(api, s, dialogue="b").json()
    assert (got["camera"], got["dialogue"]) == ("orbit", "b")


def test_max_50_scenes(api):
    f = film(api)
    for _ in range(50):
        api.studio.scenes.add(f, "main", inherit=False)
    assert api.post(f"/api/films/{f}/scenes", json={}).status_code == 422


# ---------- take: keyframe + video terpilih ----------
def test_status_follows_keyframe_and_clip(api):
    s = scene(api, film(api))["id"]
    img = up(api)
    assert put(api, s, keyframe_image_id=img).json()["status"] == "keyframe"
    done, running = clip(api), clip(api, complete=False)
    assert put(api, s, clip_id=running).json()["status"] == "video_diproses"
    assert put(api, s, clip_id=done).json()["status"] == "siap"
    api.studio.db.update("clips", done, {"status": "failed"})
    assert put(api, s, clip_id=done).json()["status"] == "gagal"
    assert put(api, s, keyframe_image_id=None, clip_id=None).json()["status"] == "naskah"


def test_scene_from_clip_uses_clip_source_as_keyframe(api):
    f, c = film(api), clip(api)
    s = scene(api, f, clip_id=c)
    assert s["clip_id"] == c and s["keyframe_image_id"] and s["status"] == "siap"
    ep = api.get(f"/api/films/{f}").json()
    assert ep["clip_ids"] == [c] and ep["scene_count"] == 1 and ep["ready_count"] == 1


def test_deleting_keyframe_image_clears_it_from_scene(api):
    f = film(api)
    s = scene(api, f)["id"]
    img = up(api)
    put(api, s, keyframe_image_id=img)
    assert api.delete(f"/api/images/{img}").status_code == 200
    assert api.get(f"/api/films/{f}").json()["scenes"][0]["keyframe_image_id"] is None


def test_rendering_episode_blocks_structure_but_not_text(api):
    f = film(api)
    s = scene(api, f)["id"]
    api.studio.db.update("films", f, {"render_status": "rendering"})
    assert api.post(f"/api/films/{f}/scenes", json={}).status_code == 409
    assert api.delete(f"/api/scenes/{s}").status_code == 409
    assert api.put(f"/api/films/{f}/scene-order", json={"scene_ids": [s]}).status_code == 409
    assert put(api, s, clip_id=clip(api)).status_code == 409
    assert put(api, s, dialogue="boleh").status_code == 200


def test_render_requires_a_video_in_every_scene(api):
    f = film(api)
    scene(api, f, clip_id=clip(api))
    scene(api, f)
    r = api.post(f"/api/films/{f}/render")
    assert r.status_code == 409 and "adegan 2" in r.json()["detail"]
    detail = api.get(f"/api/films/{f}").json()
    assert [w["scene"] for w in detail["warnings"] if w["kind"] == "unplayable"] == [2]


# ---------- latar ----------
def test_location_crud_and_delete_detaches_scenes(api):
    f, img = film(api), up(api)
    loc = api.post("/api/locations", json={"name": "Pasar", "description": "ramai", "image_id": img}).json()
    assert api.post("/api/locations", json={"name": "  "}).status_code == 422
    assert api.post("/api/locations", json={"name": "x", "description": "y" * 301}).status_code == 422
    s = scene(api, f)["id"]
    put(api, s, location_id=loc["id"])
    assert api.get("/api/locations").json()[0]["used"] == 1
    assert api.put(f"/api/locations/{loc['id']}", json={"name": "Pasar Pagi"}).json()["name"] == "Pasar Pagi"
    assert api.put(f"/api/locations/{loc['id']}", json={"image_id": "tidak-ada"}).status_code == 404
    assert api.delete(f"/api/images/{img}").status_code == 409                       # gambar latar dijaga
    assert api.delete(f"/api/locations/{loc['id']}").status_code == 200
    assert api.get(f"/api/films/{f}").json()["scenes"][0]["location"] is None       # adegan tetap ada
    assert api.delete(f"/api/images/{img}").status_code == 200                        # setelah latar dihapus boleh


# ---------- tampilan / baju ----------
def test_outfit_needs_image_or_description_and_guards_its_image(api):
    cid, _ = char(api)
    img = up(api)
    assert api.post(f"/api/characters/{cid}/outfits", json={"name": "Kosong"}).status_code == 422
    o = api.post(f"/api/characters/{cid}/outfits", json={"name": "Kebaya", "image_id": img}).json()
    assert api.get(f"/api/characters/{cid}/outfits").json()[0]["id"] == o["id"]
    assert api.get("/api/characters").json()[0]["outfits"][0]["name"] == "Kebaya"
    assert api.delete(f"/api/images/{img}").status_code == 409
    assert api.put(f"/api/outfits/{o['id']}", json={"image_id": None}).status_code == 422   # jadi kosong total
    assert api.put(f"/api/outfits/{o['id']}", json={"description": "merah", "image_id": None}).status_code == 200
    assert api.delete(f"/api/images/{img}").status_code == 200


def test_deleting_outfit_and_character_release_scenes(api):
    f, (cid, _) = film(api), char(api)
    o = api.post(f"/api/characters/{cid}/outfits", json={"name": "Jas", "description": "jas"}).json()["id"]
    s = scene(api, f)["id"]
    put(api, s, cast=[{"character_id": cid, "outfit_id": o, "action": "duduk"}])
    assert api.delete(f"/api/outfits/{o}").status_code == 200
    cast = api.get(f"/api/films/{f}").json()["scenes"][0]["cast"]
    assert cast[0]["outfit_id"] is None and cast[0]["action"] == "duduk"
    assert api.delete(f"/api/characters/{cid}").status_code == 200
    db = api.studio.db
    assert api.get(f"/api/films/{f}").json()["scenes"][0]["cast"] == []
    assert db.one("SELECT COUNT(*) AS n FROM outfits")["n"] == 0 and db.one("SELECT COUNT(*) AS n FROM scene_cast")["n"] == 0


# ---------- workspace ----------
def test_scene_data_is_isolated_between_workspaces(api):
    b = mkws(api, "B")
    fb, locb = film(api, b), api.post("/api/locations", json={"name": "Hutan"}, **hdr(b)).json()["id"]
    sb = scene(api, fb, b)["id"]
    assert api.get("/api/locations").json() == []
    fm = film(api)
    sm = scene(api, fm)["id"]
    assert put(api, sm, location_id=locb).status_code == 404                   # latar milik B
    assert put(api, sm, keyframe_image_id=up(api, b)).status_code == 404
    assert put(api, sm, cast=[{"character_id": char(api, b)[0]}]).status_code == 404
    assert api.put(f"/api/films/{fm}/scene-order", json={"scene_ids": [sb]}).status_code == 409
    assert api.post(f"/api/films/{fb}/scenes", json={}).status_code == 404    # film B dari header Utama


def test_workspace_delete_removes_scene_tables(api):
    b = mkws(api, "B")
    fb = film(api, b)
    cid, _ = char(api, b)
    api.post(f"/api/characters/{cid}/outfits", json={"name": "Jas", "description": "jas"}, **hdr(b))
    loc = api.post("/api/locations", json={"name": "Hutan"}, **hdr(b)).json()["id"]
    put(api, scene(api, fb, b)["id"], b, location_id=loc, cast=[{"character_id": cid}])
    archive(api, b)
    assert api.delete(f"/api/workspaces/{b}").status_code == 200
    db = api.studio.db
    for table in ("scenes", "scene_cast", "outfits", "locations"):
        assert db.one(f"SELECT COUNT(*) AS n FROM {table}")["n"] == 0, table


def test_copy_character_copies_outfits_with_their_images(api):
    b = mkws(api, "B")
    cid, _ = char(api)
    img = up(api)
    api.post(f"/api/characters/{cid}/outfits", json={"name": "Kebaya", "image_id": img})
    api.post(f"/api/characters/{cid}/outfits", json={"name": "Teks", "description": "jas hujan"})
    r = api.post(f"/api/workspaces/{b}/copy", json={"character_ids": [cid]})
    assert r.status_code == 200, r.text
    new = r.json()["characters"][0]["to"]
    outs = api.get(f"/api/characters/{new}/outfits", **hdr(b)).json()
    assert [o["name"] for o in outs] == ["Kebaya", "Teks"]
    assert outs[0]["image_id"] and outs[0]["image_id"] != img and outs[1]["image_id"] is None
    assert api.get(f"/api/images/{outs[0]['image_id']}/file").status_code == 200
    assert api.get(f"/api/characters/{cid}/outfits").json()[0]["image_id"] == img        # asli tak berubah


def test_populated_workspace_deletes_cleanly_with_scenes(api):
    """populate() membuat film dengan adegan dari klip; hapus workspace tidak boleh menyisakan adegan."""
    b = mkws(api, "B")
    populate(api, b)
    assert api.studio.db.one("SELECT COUNT(*) AS n FROM scenes")["n"] >= 1
    archive(api, b)
    assert api.delete(f"/api/workspaces/{b}").status_code == 200
    assert api.studio.db.one("SELECT COUNT(*) AS n FROM scenes")["n"] == 0


# ---------- migrasi ----------
def test_migration_v8_to_v9_turns_old_films_into_episodes(tmp_path):
    path = tmp_path / "v8.db"
    db = Database(path)
    for cid, deleted in (("c1", None), ("c2", None), ("gone", "t")):
        db.execute("INSERT INTO clips (id, prompt, model, params, status, created_at, updated_at, workspace_id, deleted_at) "
                   "VALUES (?, 'p', 'm', '{}', 'completed', 't', 't', 'main', ?)", (cid, deleted))
    db.execute("INSERT INTO films (id, title, clip_ids, created_at, updated_at, workspace_id) VALUES ('f1', 'Lama', ?, '1', '1', 'main')",
               (json.dumps(["c1", "c2", "c1", "gone"]),))
    db.execute("INSERT INTO films (id, title, clip_ids, created_at, updated_at, workspace_id) VALUES ('f2', 'Kosong', '[]', '2', '2', 'main')")
    for col in ("number", "synopsis", "aspect_ratio"):
        db._conn.execute(f"ALTER TABLE films DROP COLUMN {col}")
    for table in ("scenes", "scene_cast", "locations", "outfits"):
        db._conn.execute(f"DROP TABLE {table}")
    db._conn.execute("PRAGMA user_version = 8")
    db._conn.commit()
    db2 = Database(path)
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == 18
    films = db2.all("SELECT id, number, synopsis, aspect_ratio FROM films ORDER BY number")
    assert films == [{"id": "f1", "number": 1, "synopsis": "", "aspect_ratio": "16:9"},
                     {"id": "f2", "number": 2, "synopsis": "", "aspect_ratio": "16:9"}]
    scenes = db2.all("SELECT position, clip_id FROM scenes WHERE film_id = 'f1' ORDER BY position")
    assert [(s["position"], s["clip_id"]) for s in scenes] == [(0, "c1"), (1, "c2"), (2, "c1"), (3, None)]   # duplikat tetap, klip terhapus = adegan kosong
    assert db2.one("SELECT COUNT(*) AS n FROM scenes WHERE film_id = 'f2'")["n"] == 0
    Database(path)                                                                       # migrasi kedua kali tidak menggandakan
    assert db2.one("SELECT COUNT(*) AS n FROM scenes")["n"] == 4


# ---------- hapus banyak adegan (plan 18 Revisi 3) ----------
def test_bulk_delete_scenes_is_atomic_renumbers_once_and_detaches_results(api):
    f, (cid, img) = film(api), char(api)
    ids = [scene(api, f)["id"] for _ in range(5)]
    put(api, ids[1], cast=[{"character_id": cid, "outfit_id": None, "action": "lari"}])
    api.put(f"/api/scenes/{ids[1]}/beats", json={"beats": [{"start": 0, "end": 3, "cast": [cid]}]})
    api.studio.db.execute("UPDATE images SET scene_id = ? WHERE id = ?", (ids[1], img))
    r = api.post(f"/api/films/{f}/scenes/bulk-delete", json={"scene_ids": [ids[1], ids[3], ids[1]]})   # duplikat diabaikan
    assert r.status_code == 200 and r.json()["deleted"] == 2 and r.json()["remaining"] == 3
    assert numbers(api, f) == [(1, ids[0]), (2, ids[2]), (3, ids[4])]                       # urutan 1..n tanpa lubang
    db = api.studio.db
    assert db.one("SELECT COUNT(*) AS n FROM scene_cast WHERE scene_id = ?", (ids[1],))["n"] == 0
    assert db.one("SELECT COUNT(*) AS n FROM scene_beats WHERE scene_id = ?", (ids[1],))["n"] == 0
    assert db.one("SELECT scene_id FROM images WHERE id = ?", (img,))["scene_id"] is None  # gambar tetap ada, hanya terlepas


def test_bulk_delete_scenes_rejects_foreign_ids_empty_and_rendering_without_partial_effect(api):
    f, other = film(api), film(api, title="Lain")
    mine, theirs = scene(api, f)["id"], scene(api, other)["id"]
    assert api.post(f"/api/films/{f}/scenes/bulk-delete", json={"scene_ids": [mine, theirs]}).status_code == 404
    assert api.post(f"/api/films/{f}/scenes/bulk-delete", json={"scene_ids": []}).status_code == 422
    assert numbers(api, f) == [(1, mine)] and len(numbers(api, other)) == 1                  # ditolak = tidak ada yang terhapus
    api.studio.db.execute("UPDATE films SET render_status = 'rendering' WHERE id = ?", (f,))
    assert api.post(f"/api/films/{f}/scenes/bulk-delete", json={"scene_ids": [mine]}).status_code == 409
    b = mkws(api, "B")
    assert api.post(f"/api/films/{f}/scenes/bulk-delete", json={"scene_ids": [mine]}, **hdr(b)).status_code == 404   # episode workspace lain
