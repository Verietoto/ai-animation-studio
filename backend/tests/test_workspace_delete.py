import time

import pytest

from app.db import Database
from test_workspaces import VIDEO, char, clip, count, hdr, mkws, up


def archive(api, wid):
    assert api.post(f"/api/workspaces/{wid}/archive").status_code == 200


def listed(api, archived=False):
    return {w["id"]: w for w in api.get("/api/workspaces" + ("?archived=true" if archived else "")).json()}


def wait_film(api, film_id, wid, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        film = api.get(f"/api/films/{film_id}", **hdr(wid)).json()
        if film["render_status"] == "done":
            return
        time.sleep(0.1)
    raise AssertionError("render film tidak selesai")


def files_of(api, wid):
    """Semua file di disk yang dimiliki workspace (dari DB), sebagai Path."""
    db, st = api.studio.db, api.studio.storage
    stored = [r["path"] for r in db.all("SELECT path FROM images WHERE workspace_id = ?", (wid,))]
    for r in db.all("SELECT path, merged_path FROM clips WHERE workspace_id = ?", (wid,)):
        stored += [r["path"], r["merged_path"]]
    stored += [r["merged_path"] for r in db.all("SELECT merged_path FROM films WHERE workspace_id = ?", (wid,))]
    stored += [r["path"] for r in db.all("SELECT path FROM refs WHERE workspace_id = ? AND source_clip_id IS NULL", (wid,))]
    return [st.resolve(p) for p in stored if p]


def populate(api, wid):
    """Isi workspace dengan semua jenis aset: gambar, klip (+ extend + gabung), karakter + sheet, film dirender, dua referensi video."""
    h = hdr(wid)
    c1 = clip(api, wid)
    c2 = api.post(f"/api/clips/{c1}/extend", json={"prompt": "lanjut", "model": VIDEO["model"]}, **h).json()["id"]
    api.studio.poll_once()
    assert api.post(f"/api/clips/{c2}/merge", **h).status_code == 200            # menghasilkan merged_path
    cid, _ = char(api, wid)
    api.studio.add_character_image(cid, up(api, wid), "front", wid)
    film = api.post("/api/films", json={"title": "F"}, **h).json()["id"]
    api.post(f"/api/films/{film}/scenes", json={"clip_id": c1}, **h)
    assert api.post(f"/api/films/{film}/render", **h).status_code == 202
    wait_film(api, film, wid)
    own = api.studio.storage.save(b"video-unggahan", ".mp4")                      # referensi unggahan sendiri
    clip_path = api.studio.db.one("SELECT path FROM clips WHERE id = ?", (c1,))["path"]
    for rid, path, src in (("ref-own", str(own), None), ("ref-clip", clip_path, c1)):   # "dari klip" memakai file klip
        api.studio.db.insert("refs", {"id": f"{rid}-{wid[:6]}", "path": path, "source_clip_id": src, "duration": 1.0, "width": 10,
                                      "height": 10, "has_audio": 0, "created_at": "t", "workspace_id": wid})
    files = files_of(api, wid)
    assert len(files) >= 8 and all(p.exists() for p in files)
    return files


# ---------- pulihkan ----------
def test_restore_brings_workspace_back(api):
    b = mkws(api, "B")
    archive(api, b)
    assert b not in listed(api) and listed(api, True)[b]["archived"] is True
    r = api.post(f"/api/workspaces/{b}/restore")
    assert r.status_code == 200 and r.json()["archived"] is False
    assert b in listed(api) and api.get("/api/images", **hdr(b)).status_code == 200
    assert api.post(f"/api/workspaces/{b}/restore").status_code == 409            # tidak sedang diarsip
    assert api.post("/api/workspaces/tidak-ada/restore").status_code == 404


# ---------- hapus: penolakan ----------
def test_delete_rules(api):
    b = mkws(api, "B")
    running = clip(api, b, complete=False)
    film = api.post("/api/films", json={"title": "F"}, **hdr(b)).json()["id"]
    assert api.delete(f"/api/workspaces/{b}").status_code == 409                   # belum diarsip
    assert api.delete("/api/workspaces/main").status_code == 400                   # Utama
    archive(api, b)
    r = api.delete(f"/api/workspaces/{b}")
    assert r.status_code == 409 and "job video" in r.json()["detail"]              # job masih berjalan
    api.studio.poll_once()
    api.studio.db.update("films", film, {"render_status": "rendering"})
    assert api.delete(f"/api/workspaces/{b}").status_code == 409                   # film sedang dirender
    api.studio.db.update("films", film, {"render_status": "idle"})
    assert api.get(f"/api/clips/{running}/file").status_code == 200                # tak ada yang berubah oleh penolakan
    assert api.delete(f"/api/workspaces/{b}").status_code == 200
    assert api.delete(f"/api/workspaces/{b}").status_code == 404                   # sudah tombstone


# ---------- hapus: berhasil ----------
def test_delete_removes_files_keeps_cost_and_frees_the_name(api):
    control = up(api)                                                              # milik Utama, tidak boleh tersentuh
    b = mkws(api, "Proyek A")
    files = populate(api, b)
    img_b = api.studio.db.one("SELECT id FROM images WHERE workspace_id = ? LIMIT 1", (b,))["id"]
    copy_id = api.post("/api/workspaces/main/copy", json={"image_ids": [img_b]}, **hdr(b)).json()["images"][0]["to"]
    spent, expected = api.studio.db.committed_today(), api.studio.workspaces._counts(b)
    archive(api, b)
    r = api.delete(f"/api/workspaces/{b}")
    assert r.status_code == 200 and r.json()["deleted"] == expected
    assert api.studio.db.committed_today() == pytest.approx(spent)                 # catatan biaya tetap utuh
    assert not any(p.exists() for p in files)                                      # file hilang dari disk
    db = api.studio.db
    for table in ("characters", "films", "refs"):
        assert count(api, table, b) == 0, table
    assert db.one("SELECT COUNT(*) AS n FROM character_images WHERE character_id NOT IN (SELECT id FROM characters)")["n"] == 0
    assert db.one("SELECT COUNT(*) AS n FROM images WHERE workspace_id = ? AND deleted_at IS NULL", (b,))["n"] == 0
    assert db.one("SELECT COUNT(*) AS n FROM clips WHERE workspace_id = ? AND deleted_at IS NULL", (b,))["n"] == 0
    assert db.one("SELECT COUNT(*) AS n FROM images WHERE workspace_id = ?", (b,))["n"] > 0     # baris biaya tetap ada
    row = db.one("SELECT name, deleted_at FROM workspaces WHERE id = ?", (b,))
    assert row["deleted_at"] and row["name"].startswith("Proyek A (dihapus ")
    assert b not in listed(api, True)                                              # tidak muncul di daftar mana pun
    miss = api.get("/api/images", **hdr(b))
    assert miss.status_code == 404 and miss.json()["code"] == "workspace_missing"  # tab lain yang masih memakainya
    assert api.put(f"/api/workspaces/{b}", json={"name": "X"}).status_code == 404
    assert api.post(f"/api/workspaces/{b}/archive").status_code == 404
    assert api.post(f"/api/workspaces/{b}/restore").status_code == 404
    assert api.post(f"/api/workspaces/{b}/copy", json={"image_ids": [control]}).status_code == 404
    assert api.post("/api/workspaces", json={"name": "Proyek A"}).status_code == 200   # nama bisa dipakai ulang
    assert not [j for j in api.get("/api/jobs").json() if j["workspace_id"] == b]
    # salinan di workspace lain utuh; keterangan asal bermakna; milik Utama tidak tersentuh
    assert api.get(f"/api/images/{copy_id}/file").status_code == 200
    origin = {i["id"]: i for i in api.get("/api/images").json()}[copy_id]["origin_workspace"]
    assert origin.startswith("Proyek A (dihapus ")
    assert api.get(f"/api/images/{control}/file").status_code == 200


def test_failed_transaction_keeps_files_and_rows(api):
    b = mkws(api, "B")
    files = populate(api, b)
    archive(api, b)
    api.studio.db._conn.execute("CREATE TRIGGER boom BEFORE UPDATE ON workspaces WHEN NEW.deleted_at IS NOT NULL "
                                "BEGIN SELECT RAISE(ABORT, 'boom'); END")
    with pytest.raises(Exception):
        api.delete(f"/api/workspaces/{b}")
    assert all(p.exists() for p in files)                                          # file dihapus SETELAH commit
    assert count(api, "characters", b) == 1 and count(api, "films", b) == 1        # transaksi dibatalkan utuh
    api.studio.db._conn.execute("DROP TRIGGER boom")
    assert api.delete(f"/api/workspaces/{b}").status_code == 200
    assert not any(p.exists() for p in files)


def test_delete_empty_workspace(api):
    b = mkws(api, "Kosong")
    archive(api, b)
    r = api.delete(f"/api/workspaces/{b}")
    assert r.status_code == 200 and r.json()["deleted"] == {"images": 0, "clips": 0, "characters": 0, "films": 0}


# ---------- migrasi ----------
def test_migration_v7_to_v8_adds_deleted_at(tmp_path):
    path = tmp_path / "v7.db"
    db = Database(path)
    db._conn.execute("ALTER TABLE workspaces DROP COLUMN deleted_at")
    db._conn.execute("PRAGMA user_version = 7")
    db._conn.commit()
    db2 = Database(path)
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == 20
    assert db2.one("SELECT id, deleted_at FROM workspaces WHERE id = 'main'") == {"id": "main", "deleted_at": None}
