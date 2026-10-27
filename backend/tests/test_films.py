import json
import subprocess
import time

import pytest

from app import media
from app.db import Database
from conftest import upload

VIDEO = {"model": "bytedance/seedance-2.5", "prompt": "adegan", "duration": 4, "resolution": "720p", "aspect_ratio": "16:9"}


def make_clip(api, complete=True) -> str:
    img = upload(api)
    clip = api.post("/api/clips", json={**VIDEO, "image_id": img["id"]}).json()
    if complete:
        api.studio.poll_once()
    return clip["id"]


def new_film(api, ids=(), title="Film uji") -> dict:
    film = api.post("/api/films", json={"title": title}).json()
    for cid in ids:
        api.post(f"/api/films/{film['id']}/scenes", json={"clip_id": cid})
    return api.get(f"/api/films/{film['id']}").json()


def wait_render(api, film_id, status="done", timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        film = api.get(f"/api/films/{film_id}").json()
        if film["render_status"] == status:
            return film
        time.sleep(0.1)
    raise AssertionError(f"render tidak mencapai {status}: {film}")


def test_crud_order_and_validation(api):
    a, b = make_clip(api), make_clip(api)
    film = new_film(api, [b, a, b])           # duplikat diperbolehkan, urutan dipertahankan
    assert film["clip_ids"] == [b, a, b] and film["render_status"] == "idle" and not film["has_file"]
    assert api.put(f"/api/films/{film['id']}", json={"title": "Baru"}).json()["title"] == "Baru"
    assert api.get("/api/films").json()[0]["id"] == film["id"]
    assert api.post("/api/films", json={"title": "  "}).status_code == 422
    assert api.put(f"/api/films/{film['id']}", json={"clip_ids": [a]}).status_code == 422   # tidak dipakai lagi (plan 08)
    assert api.post(f"/api/films/{film['id']}/scenes", json={"clip_id": "tidak-ada"}).status_code == 404
    assert api.get("/api/films/nope").status_code == 404
    assert api.delete(f"/api/films/{film['id']}").status_code == 200
    assert api.get(f"/api/films/{film['id']}").status_code == 404


def test_clip_duration_saved_on_download(api):
    clip = api.get(f"/api/clips/{make_clip(api)}").json()
    assert clip["duration"] == pytest.approx(1.0, abs=0.2)


def test_render_rejects_empty_and_unfinished(api):
    assert api.post(f"/api/films/{new_film(api)['id']}/render").status_code == 422
    done, pending = make_clip(api), make_clip(api, complete=False)
    r = api.post(f"/api/films/{new_film(api, [done, pending])['id']}/render")
    assert r.status_code == 409 and "adegan 2" in r.json()["detail"]


def test_render_is_async_and_produces_playable_film(api):
    ids = [make_clip(api), make_clip(api)]
    film = new_film(api, ids)
    r = api.post(f"/api/films/{film['id']}/render")
    assert r.status_code == 202 and r.json()["render_status"] in {"rendering", "done"}
    done = wait_render(api, film["id"])
    assert done["has_file"] and not done["stale"] and done["render_error"] is None
    data = api.get(f"/api/films/{film['id']}/file")
    assert data.status_code == 200 and len(data.content) > 1000
    assert sum(done["durations"].values()) == pytest.approx(2.0, abs=0.5)


def test_stale_after_edit_and_old_render_file_removed(api):
    a, b = make_clip(api), make_clip(api)
    film = new_film(api, [a])
    api.post(f"/api/films/{film['id']}/render")
    wait_render(api, film["id"])
    old = api.studio.db.one("SELECT merged_path FROM films WHERE id = ?", (film["id"],))["merged_path"]
    api.post(f"/api/films/{film['id']}/scenes", json={"clip_id": b})
    assert api.get(f"/api/films/{film['id']}").json()["stale"] is True
    api.post(f"/api/films/{film['id']}/render")
    wait_render(api, film["id"])
    after = api.get(f"/api/films/{film['id']}").json()
    assert after["stale"] is False
    new = api.studio.db.one("SELECT merged_path FROM films WHERE id = ?", (film["id"],))["merged_path"]
    assert new != old and not api.studio.storage.resolve(old).exists()   # file lama tidak menumpuk


def test_rendering_film_cannot_be_changed_deleted_or_rendered_twice(api):
    film = new_film(api, [make_clip(api)])
    api.studio.db.update("films", film["id"], {"render_status": "rendering"})
    assert api.post(f"/api/films/{film['id']}/render").status_code == 409
    assert api.put(f"/api/films/{film['id']}", json={"title": "x"}).status_code == 409
    assert api.delete(f"/api/films/{film['id']}").status_code == 409


def test_failed_render_is_reported_and_can_be_retried(api, monkeypatch):
    film = new_film(api, [make_clip(api)])
    real = media.merge_videos
    monkeypatch.setattr(media, "merge_videos", lambda *a, **k: (_ for _ in ()).throw(media.MediaError("disk penuh")))
    api.post(f"/api/films/{film['id']}/render")
    failed = wait_render(api, film["id"], "failed")
    assert "disk penuh" in failed["render_error"] and not failed["has_file"]
    monkeypatch.setattr(media, "merge_videos", real)
    api.post(f"/api/films/{film['id']}/render")
    assert wait_render(api, film["id"])["has_file"]


def test_interrupted_render_is_marked_failed_on_startup(api):
    film = new_film(api, [make_clip(api)])
    api.studio.db.update("films", film["id"], {"render_status": "rendering"})
    api.studio.films.recover()
    got = api.get(f"/api/films/{film['id']}").json()
    assert got["render_status"] == "failed" and "terputus" in got["render_error"]


def test_aspect_ratio_mismatch_is_warned(api, tmp_path):
    a, b = make_clip(api), make_clip(api)
    portrait = tmp_path / "portrait.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=green:s=90x160:d=1:r=24",
                    "-pix_fmt", "yuv420p", str(portrait)], check=True)
    stored = api.studio.storage.save(portrait.read_bytes(), ".mp4")
    api.studio.db.update("clips", b, {"path": str(stored)})
    detail = api.get(f"/api/films/{new_film(api, [a, b])['id']}").json()
    assert [w["scene"] for w in detail["warnings"] if w["kind"] == "aspect"] == [2]
    assert not [w for w in detail["warnings"] if w["kind"] == "unplayable"]


def test_delete_removes_render_file(api):
    film = new_film(api, [make_clip(api)])
    api.post(f"/api/films/{film['id']}/render")
    wait_render(api, film["id"])
    path = api.studio.storage.resolve(api.studio.db.one("SELECT merged_path FROM films WHERE id = ?", (film["id"],))["merged_path"])
    assert path.exists() and api.delete(f"/api/films/{film['id']}").status_code == 200
    assert not path.exists()


def test_migration_v4_to_v5_keeps_existing_rows(tmp_path):
    path = tmp_path / "old.db"
    db = Database(path)
    db.execute("INSERT INTO clips (id, prompt, model, params, status, created_at, updated_at) "
               "VALUES ('c1', 'p', 'm', '{}', 'completed', 't', 't')")
    db._conn.execute("ALTER TABLE clips DROP COLUMN duration")   # bentuk skema v4
    db._conn.execute("DROP TABLE films")
    db._conn.execute("PRAGMA user_version = 4")
    db._conn.commit()
    db2 = Database(path)
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == 18   # v4 -> v5 -> ... -> v18
    row = db2.one("SELECT id, duration FROM clips WHERE id = 'c1'")
    assert row == {"id": "c1", "duration": None}
    db2.insert("films", {"id": "f", "title": "t", "created_at": "t", "updated_at": "t"})
    assert json.loads(db2.one("SELECT clip_ids FROM films")["clip_ids"]) == []
