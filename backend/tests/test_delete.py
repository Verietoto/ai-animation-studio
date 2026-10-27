import pytest

from app.db import Database
from conftest import upload

VIDEO = {"model": "bytedance/seedance-2.5", "prompt": "adegan", "duration": 4, "resolution": "720p", "aspect_ratio": "16:9"}


def make_clip(api, complete=True) -> str:
    clip = api.post("/api/clips", json={**VIDEO, "image_id": upload(api)["id"]}).json()
    if complete:
        api.studio.poll_once()
    return clip["id"]


def clip_file(api, clip_id):
    row = api.studio.db.one("SELECT path FROM clips WHERE id = ?", (clip_id,))
    return api.studio.storage.resolve(row["path"]) if row["path"] else None


def test_delete_image_hides_it_removes_file_and_keeps_cost_record(api):
    src = upload(api)
    edited = api.post(f"/api/images/{src['id']}/edit",
                      json={"prompt": "x", "model": "openai/gpt-image-2", "reference_image_ids": []}).json()[0]
    path = api.studio.storage.resolve(api.studio.db.one("SELECT path FROM images WHERE id = ?", (edited["id"],))["path"])
    spent = api.studio.db.committed_today()
    assert path.exists() and spent > 0
    assert api.delete(f"/api/images/{edited['id']}").json() == {"ok": True}
    assert edited["id"] not in [i["id"] for i in api.get("/api/images").json()]
    assert api.get(f"/api/images/{edited['id']}/file").status_code == 404
    assert not path.exists()
    assert api.studio.db.committed_today() == pytest.approx(spent)   # batas harian tidak bisa "dikembalikan" dengan menghapus
    assert api.delete(f"/api/images/{edited['id']}").status_code == 404


def test_image_used_by_character_cannot_be_deleted_until_character_is(api):
    img = upload(api)
    char = api.post("/api/characters", json={"name": "Rina", "description": "rambut bob", "source_image_id": img["id"]}).json()
    r = api.delete(f"/api/images/{img['id']}")
    assert r.status_code == 409 and "Rina" in r.json()["detail"]
    assert api.delete(f"/api/characters/{char['id']}").status_code == 200
    assert api.get("/api/characters").json() == []
    assert api.delete(f"/api/images/{img['id']}").status_code == 200   # gambar tetap ada sampai dihapus sendiri
    assert api.delete(f"/api/characters/{char['id']}").status_code == 404


def test_image_used_by_running_job_cannot_be_deleted(api):
    img = upload(api)
    clip = api.post("/api/clips", json={**VIDEO, "image_id": img["id"]}).json()
    assert clip["status"] == "submitted"
    assert api.delete(f"/api/images/{img['id']}").status_code == 409


def test_clip_rules_and_cleanup(api):
    parent = make_clip(api)
    child = api.post(f"/api/clips/{parent}/extend", json={"prompt": "lanjut", "model": VIDEO["model"]}).json()["id"]
    api.studio.poll_once()
    spent = api.studio.db.committed_today()
    files = [clip_file(api, parent), clip_file(api, child)]
    assert api.delete(f"/api/clips/{parent}").status_code == 409          # punya lanjutan
    assert api.delete(f"/api/clips/{child}").status_code == 200
    assert api.delete(f"/api/clips/{parent}").status_code == 200
    assert api.get("/api/clips").json() == [] and not any(f.exists() for f in files)
    assert api.get(f"/api/clips/{parent}").status_code == 404
    assert api.post(f"/api/clips/{parent}/extend", json={"prompt": "x", "model": VIDEO["model"]}).status_code == 404
    assert api.studio.db.committed_today() == pytest.approx(spent)
    assert api.delete(f"/api/clips/{parent}").status_code == 404


def test_running_clip_cannot_be_deleted(api):
    assert api.delete(f"/api/clips/{make_clip(api, complete=False)}").status_code == 409


def test_deleting_clip_detaches_it_from_films(api):
    a, b = make_clip(api), make_clip(api)
    film = api.post("/api/films", json={"title": "F"}).json()
    for cid in (a, b, a):
        api.post(f"/api/films/{film['id']}/scenes", json={"clip_id": cid})
    assert api.delete(f"/api/clips/{a}").status_code == 200
    got = api.get(f"/api/films/{film['id']}").json()
    assert got["clip_ids"] == [b] and len(got["scenes"]) == 3                 # adegan tetap ada, hanya videonya yang lepas
    assert [s["status"] for s in got["scenes"]] == ["keyframe", "siap", "keyframe"]   # gambar sumber klip tetap jadi keyframe adegan
    assert api.post(f"/api/films/{film['id']}/scenes", json={"clip_id": a}).status_code == 404   # klip terhapus tak bisa dipakai lagi


def test_clip_in_rendering_film_is_not_deleted(api):
    a = make_clip(api)
    film = api.post("/api/films", json={"title": "F"}).json()
    api.post(f"/api/films/{film['id']}/scenes", json={"clip_id": a})
    api.studio.db.update("films", film["id"], {"render_status": "rendering"})
    assert api.delete(f"/api/clips/{a}").status_code == 409
    assert api.get(f"/api/clips/{a}").status_code == 200                                      # tidak ada yang berubah
    assert api.get(f"/api/films/{film['id']}").json()["clip_ids"] == [a]


def test_migration_v5_to_v6_adds_deleted_at(tmp_path):
    path = tmp_path / "v5.db"
    db = Database(path)
    db.execute("INSERT INTO clips (id, prompt, model, params, status, created_at, updated_at) "
               "VALUES ('c1', 'p', 'm', '{}', 'completed', 't', 't')")
    for table in ("images", "clips"):
        db._conn.execute(f"ALTER TABLE {table} DROP COLUMN deleted_at")
    db._conn.execute("PRAGMA user_version = 5")
    db._conn.commit()
    db2 = Database(path)
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == 18   # v5 -> v6 -> ... -> v18
    assert db2.one("SELECT id, deleted_at FROM clips") == {"id": "c1", "deleted_at": None}
