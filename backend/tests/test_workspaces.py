import re
from pathlib import Path

import pytest

from app.db import Database
from conftest import png_bytes

VIDEO = {"model": "bytedance/seedance-2.5", "prompt": "adegan", "duration": 4, "resolution": "720p", "aspect_ratio": "16:9"}
EDIT_MODEL = "openai/gpt-image-2"
FILE_SUFFIXES = ("/file", "/merged", "/sketch")   # berkas hanya-baca: tanpa batas workspace (plan 07 grill 1)
ID_PARAMS = {"image_id": "image", "clip_id": "clip", "character_id": "character", "film_id": "film", "ref_id": "ref",
             "scene_id": "scene", "location_id": "location", "outfit_id": "outfit", "voice_id": "voice"}


def hdr(ws):
    return {"headers": {"X-Workspace-Id": ws}}


def mkws(api, name):
    r = api.post("/api/workspaces", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def up(api, ws=None, color=(200, 50, 50)):
    r = api.post("/api/images", files={"file": ("a.png", png_bytes(color), "image/png")}, **(hdr(ws) if ws else {}))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def clip(api, ws=None, complete=True):
    kw = hdr(ws) if ws else {}
    img = up(api, ws)
    c = api.post("/api/clips", json={**VIDEO, "image_id": img}, **kw).json()
    if complete:
        api.studio.poll_once()
    return c["id"]


def char(api, ws=None, name="Rina"):
    kw = hdr(ws) if ws else {}
    img = up(api, ws)
    r = api.post("/api/characters", json={"name": name, "description": "bob hitam", "source_image_id": img}, **kw)
    assert r.status_code == 200, r.text
    return r.json()["id"], img


def count(api, table, ws):
    return api.studio.db.one(f"SELECT COUNT(*) AS n FROM {table} WHERE workspace_id = ?", (ws,))["n"]


# ---------- migrasi ----------
def test_migration_v6_to_v7_moves_everything_into_main(tmp_path):
    path = tmp_path / "v6.db"
    db = Database(path)
    db.execute("INSERT INTO images (id, kind, path, created_at) VALUES ('i1', 'upload', 'p', 't')")
    db.execute("INSERT INTO clips (id, prompt, model, params, status, created_at, updated_at) VALUES ('c1', 'p', 'm', '{}', 'completed', 't', 't')")
    for t in ("images", "clips", "characters", "films"):
        db._conn.execute(f"DROP INDEX idx_{t}_ws")
    for t in ("images", "clips", "characters", "films", "refs"):
        db._conn.execute(f"ALTER TABLE {t} DROP COLUMN workspace_id")
    db._conn.execute("ALTER TABLE images DROP COLUMN origin_image_id")
    db._conn.execute("DROP TABLE workspaces")
    db._conn.execute("PRAGMA user_version = 6")
    db._conn.commit()
    db2 = Database(path)
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == 20   # v6 -> v7 -> ... -> v19
    assert db2.one("SELECT id, name FROM workspaces") == {"id": "main", "name": "Utama"}
    assert db2.one("SELECT workspace_id FROM images WHERE id = 'i1'")["workspace_id"] == "main"
    assert db2.one("SELECT workspace_id FROM clips WHERE id = 'c1'")["workspace_id"] == "main"
    Database(path)   # idempoten


def test_transaction_rolls_back_on_error(tmp_path):
    db = Database(tmp_path / "t.db")
    with pytest.raises(RuntimeError):
        with db.transaction() as tx:
            tx.insert("workspaces", {"id": "x", "name": "X", "created_at": "t", "updated_at": "t"})
            raise RuntimeError("gagal di tengah")
    assert db.one("SELECT 1 FROM workspaces WHERE id = 'x'") is None
    with db.transaction() as tx:
        tx.insert("workspaces", {"id": "y", "name": "Y", "created_at": "t", "updated_at": "t"})
    assert db.one("SELECT 1 FROM workspaces WHERE id = 'y'")


# ---------- CRUD workspace ----------
def test_workspace_crud_rules(api):
    assert [w["name"] for w in api.get("/api/workspaces").json()] == ["Utama"]
    wid = mkws(api, "Film Pendek 1")
    assert api.post("/api/workspaces", json={"name": "Film Pendek 1"}).status_code == 409
    assert api.post("/api/workspaces", json={"name": "   "}).status_code == 422
    assert api.post("/api/workspaces", json={"name": "x" * 61}).status_code == 422
    assert api.put(f"/api/workspaces/{wid}", json={"name": "Utama"}).status_code == 409
    assert api.put(f"/api/workspaces/{wid}", json={"name": "Proyek A"}).json()["name"] == "Proyek A"
    assert api.post("/api/workspaces/main/archive").status_code == 400                   # Utama tidak bisa diarsip
    assert api.post(f"/api/workspaces/{wid}/archive", **hdr(wid)).status_code == 400    # yang sedang aktif tidak bisa
    assert api.post(f"/api/workspaces/{wid}/archive").json()["archived"] is True
    assert [w["name"] for w in api.get("/api/workspaces").json()] == ["Utama"]
    assert len(api.get("/api/workspaces?archived=true").json()) == 2
    r = api.get("/api/images", **hdr(wid))
    assert r.status_code == 404 and r.json()["code"] == "workspace_missing"             # diarsip = tidak bisa dipakai
    assert api.get("/api/images", **hdr("tidak-ada")).status_code == 404


def test_response_echoes_workspace_and_default_is_main(api):
    wid = mkws(api, "B")
    assert api.get("/api/images", **hdr(wid)).headers["X-Workspace-Id"] == wid
    assert api.get("/api/images").headers["X-Workspace-Id"] == "main"


# ---------- isolasi ----------
def test_lists_are_per_workspace(api):
    b = mkws(api, "B")
    img_main, img_b = up(api), up(api, b)
    clip_b = clip(api, b)
    char_b, _ = char(api, b)
    film_b = api.post("/api/films", json={"title": "F"}, **hdr(b)).json()["id"]
    ids = lambda path, ws=None: {x["id"] for x in api.get(path, **(hdr(ws) if ws else {})).json()}   # noqa: E731
    assert img_main in ids("/api/images") and img_b not in ids("/api/images")
    assert img_b in ids("/api/images", b) and img_main not in ids("/api/images", b)
    assert clip_b in ids("/api/clips", b) and clip_b not in ids("/api/clips")
    assert char_b in ids("/api/characters", b) and char_b not in ids("/api/characters")
    assert film_b in ids("/api/films", b) and film_b not in ids("/api/films")
    counts = {w["id"]: w["counts"] for w in api.get("/api/workspaces").json()}
    assert counts[b]["clips"] == 1 and counts[b]["films"] == 1 and counts["main"]["clips"] == 0


def test_cross_workspace_operations_are_rejected(api):
    b = mkws(api, "B")
    img_b, clip_b = up(api, b), clip(api, b)
    char_b, _ = char(api, b)
    film_b = api.post("/api/films", json={"title": "F"}, **hdr(b)).json()["id"]
    img_main = up(api)
    film_main = api.post("/api/films", json={"title": "M"}).json()["id"]
    # dari workspace Utama, semua id milik B harus tidak ditemukan
    assert api.get(f"/api/clips/{clip_b}").status_code == 404
    assert api.post(f"/api/clips/{clip_b}/extend", json={"prompt": "x", "model": VIDEO["model"]}).status_code == 404
    assert api.post(f"/api/clips/{clip_b}/merge").status_code == 404
    assert api.post("/api/clips", json={**VIDEO, "image_id": img_b}).status_code == 404
    edit = lambda src, **kw: api.post(f"/api/images/{src}/edit", json={"prompt": "x", "model": EDIT_MODEL, **kw})   # noqa: E731
    assert edit(img_b).status_code == 404
    assert edit(img_main, pose_image_id=img_b).status_code == 404
    assert edit(img_main, expression_image_id=img_b).status_code == 404
    assert edit(img_main, reference_image_ids=[img_b]).status_code == 404
    assert edit(img_main, character_id=char_b).status_code == 404
    assert api.post("/api/characters", json={"name": "N", "description": "d", "source_image_id": img_b}).status_code == 404
    assert api.post("/api/estimate", json={"kind": "image_edit", "model": EDIT_MODEL, "source_image_id": img_b}).status_code == 404
    assert api.get(f"/api/films/{film_b}").status_code == 404
    assert api.put(f"/api/films/{film_b}", json={"title": "x"}).status_code == 404
    assert api.post(f"/api/films/{film_b}/render").status_code == 404
    assert api.post(f"/api/films/{film_main}/scenes", json={"clip_id": clip_b}).status_code == 404   # klip B tidak bisa masuk film Utama
    assert api.delete(f"/api/images/{img_b}").status_code == 404
    assert api.delete(f"/api/clips/{clip_b}").status_code == 404
    assert api.delete(f"/api/characters/{char_b}").status_code == 404
    assert api.post(f"/api/references/from-clip/{clip_b}").status_code == 404
    # tetap utuh di B
    assert api.get(f"/api/clips/{clip_b}", **hdr(b)).status_code == 200
    # berkas hanya-baca tetap bisa dimuat <img>/<video> tanpa header
    assert api.get(f"/api/images/{img_b}/file").status_code == 200
    assert api.get(f"/api/images/{img_b}/sketch").status_code == 200
    assert api.get(f"/api/clips/{clip_b}/file").status_code == 200


def test_every_id_route_rejects_foreign_ids(api):
    """Menyapu semua route berparameter id dari app.routes: id milik workspace lain tidak boleh pernah 2xx."""
    b = mkws(api, "B")
    foreign = {"image": up(api, b), "clip": clip(api, b), "character": char(api, b)[0],
               "film": api.post("/api/films", json={"title": "F"}, **hdr(b)).json()["id"]}
    api.studio.db.insert("refs", {"id": "ref-b", "path": "x", "duration": 1.0, "width": 10, "height": 10, "has_audio": 0,
                                  "created_at": "t", "workspace_id": b})
    foreign["ref"] = "ref-b"
    foreign["scene"] = api.post(f"/api/films/{foreign['film']}/scenes", json={}, **hdr(b)).json()["id"]
    foreign["location"] = api.post("/api/locations", json={"name": "Sawah"}, **hdr(b)).json()["id"]
    foreign["outfit"] = api.post(f"/api/characters/{foreign['character']}/outfits", json={"name": "Jas", "description": "jas hujan"},
                                 **hdr(b)).json()["id"]
    foreign["voice"] = api.studio.voices.add(foreign["character"], "suara berat", None, False, ws=b)["id"]
    swept = 0
    for route in api.raw.app.routes:
        path = getattr(route, "path", "")
        params = re.findall(r"{(\w+)}", path)
        kinds = [ID_PARAMS[p] for p in params if p in ID_PARAMS]
        if not kinds or path.endswith(FILE_SUFFIXES):
            continue
        url = path
        for p in params:
            url = url.replace("{" + p + "}", foreign[ID_PARAMS[p]])
        for method in route.methods - {"HEAD", "OPTIONS"}:
            r = api.raw.request(method, url, json={} if method in ("POST", "PUT") else None)
            assert r.status_code >= 400, f"{method} {path} menerima id workspace lain (status {r.status_code})"
            swept += 1
    assert swept >= 15   # tes tidak boleh kosong diam-diam


def test_new_rows_always_get_a_workspace_and_main_stays_untouched(api, fake):
    b = mkws(api, "B")
    before = {t: count(api, t, "main") for t in ("images", "clips", "characters", "films", "refs")}
    cid, src = char(api, b)
    sheet = up(api, b)
    api.studio.add_character_image(cid, sheet, "front", b)
    assert api.post(f"/api/images/{src}/edit", json={"prompt": "x", "model": EDIT_MODEL, "character_id": cid}, **hdr(b)).status_code == 200
    est = api.post("/api/estimate", json={"kind": "character_sheet", "model": EDIT_MODEL}, **hdr(b)).json()   # konfirmasi biaya seperti UI
    assert api.post(f"/api/characters/{cid}/sheet", json={"model": EDIT_MODEL, "confirmed_cost": est["high"]}, **hdr(b)).status_code == 200
    c1 = clip(api, b)
    c2 = api.post(f"/api/clips/{c1}/extend", json={"prompt": "lanjut", "model": VIDEO["model"]}, **hdr(b)).json()["id"]
    api.studio.poll_once()
    assert api.post(f"/api/clips/{c2}/merge", **hdr(b)).status_code == 200
    film = api.post("/api/films", json={"title": "F"}, **hdr(b)).json()["id"]
    assert api.post(f"/api/films/{film}/scenes", json={"clip_id": c1}, **hdr(b)).status_code == 200
    assert api.post(f"/api/films/{film}/scenes", json={"clip_id": c2}, **hdr(b)).status_code == 200
    for t in ("images", "clips", "characters", "films", "refs"):
        assert api.studio.db.one(f"SELECT COUNT(*) AS n FROM {t} WHERE workspace_id IS NULL")["n"] == 0
        assert count(api, t, "main") == before[t], t           # tidak ada baris bocor ke Utama
    assert count(api, "images", b) >= 6 and count(api, "clips", b) == 2


def test_jobs_lists_running_clips_from_every_workspace(api):
    b = mkws(api, "B")
    done = clip(api)                      # urutan penting: poll_once() menyelesaikan semua klip aktif
    running = clip(api, b, complete=False)
    jobs = {j["id"]: j for j in api.get("/api/jobs").json()}
    assert jobs[running]["workspace_name"] == "B" and jobs[running]["status"] == "submitted"
    assert jobs[done]["workspace_name"] == "Utama" and jobs[done]["workspace_id"] == "main"


# ---------- salin ----------
def storage_files(api):
    return sorted(p.name for p in Path(api.studio.storage.root).iterdir())


def test_copy_image_duplicates_file_and_drops_cost(api):
    b = mkws(api, "B")
    src = up(api)
    edited = api.post(f"/api/images/{src}/edit", json={"prompt": "x", "model": EDIT_MODEL, "reference_image_ids": []}).json()[0]
    spent = api.studio.db.committed_today()
    assert edited["cost"] is not None and spent > 0
    r = api.post(f"/api/workspaces/{b}/copy", json={"image_ids": [edited["id"]]})
    assert r.status_code == 200, r.text
    new_id = r.json()["images"][0]["to"]
    copy = {i["id"]: i for i in api.get("/api/images", **hdr(b)).json()}[new_id]
    assert copy["origin_image_id"] == edited["id"] and copy["parent_image_id"] is None
    assert copy["cost"] is None and copy["estimated_cost"] is None and copy["prompt"] == edited["prompt"]
    assert copy["origin_workspace"] == "Utama" and copy["kind"] == "edit"
    assert api.studio.db.committed_today() == pytest.approx(spent)     # salinan tidak menggandakan biaya hari ini
    old = api.studio.storage.resolve(api.studio.db.one("SELECT path FROM images WHERE id = ?", (edited["id"],))["path"])
    new = api.studio.storage.resolve(api.studio.db.one("SELECT path FROM images WHERE id = ?", (new_id,))["path"])
    assert old != new and new.exists() and new.read_bytes() == old.read_bytes()
    assert api.delete(f"/api/images/{edited['id']}").status_code == 200   # hapus asli tidak merusak salinan
    assert new.exists() and api.get(f"/api/images/{new_id}/file").status_code == 200


def test_copy_character_with_sheet_and_unique_names(api):
    b = mkws(api, "B")
    cid, src = char(api)
    for label in ("front", "side"):
        api.studio.add_character_image(cid, up(api), label)
    first = api.post(f"/api/workspaces/{b}/copy", json={"character_ids": [cid]}).json()
    assert first["characters"][0]["name"] == "Rina" and len(first["images"]) == 3
    copied = {c["id"]: c for c in api.get("/api/characters", **hdr(b)).json()}[first["characters"][0]["to"]]
    assert sorted(i["label"] for i in copied["images"]) == ["front", "side", "source"]
    new_src = {i["id"]: i for i in api.get("/api/images", **hdr(b)).json()}[copied["source_image_id"]]
    assert new_src["origin_image_id"] == src and copied["workspace_id"] == b
    second = api.post(f"/api/workspaces/{b}/copy", json={"character_ids": [cid]}).json()["characters"][0]["name"]
    third = api.post(f"/api/workspaces/{b}/copy", json={"character_ids": [cid]}).json()["characters"][0]["name"]
    assert (second, third) == ("Rina (salinan)", "Rina (salinan 2)")
    # menyalin salinan balik: akar nama dipakai, bukan "(salinan) (salinan)"
    again = api.post("/api/workspaces/main/copy", json={"character_ids": [copied["id"]]}, **hdr(b)).json()["characters"][0]["name"]
    assert again == "Rina (salinan)"


def test_copy_dedupes_images_shared_with_a_character(api):
    b = mkws(api, "B")
    cid, src = char(api)
    r = api.post(f"/api/workspaces/{b}/copy", json={"image_ids": [src], "character_ids": [cid]}).json()
    assert len(r["images"]) == 1 and count(api, "images", b) == 1


def test_copy_is_atomic_and_validates_target(api, monkeypatch):
    b = mkws(api, "B")
    c = mkws(api, "C")
    other = up(api, c)
    img = up(api)
    files_before = storage_files(api)
    # id milik workspace lain: ditolak sebelum ada yang disalin
    assert api.post(f"/api/workspaces/{b}/copy", json={"image_ids": [img, other]}).status_code == 404
    assert count(api, "images", b) == 0 and storage_files(api) == files_before
    # kegagalan di tengah: tidak ada baris dan tidak ada file baru
    cid, _ = char(api)
    api.studio.add_character_image(cid, up(api), "front")
    files_before = storage_files(api)
    real, calls = api.studio.storage.save, {"n": 0}

    def flaky(data, suffix):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk penuh")
        return real(data, suffix)
    monkeypatch.setattr(api.studio.storage, "save", flaky)
    with pytest.raises(OSError):
        api.post(f"/api/workspaces/{b}/copy", json={"character_ids": [cid]})
    monkeypatch.setattr(api.studio.storage, "save", real)
    assert count(api, "images", b) == 0 and count(api, "characters", b) == 0 and storage_files(api) == files_before
    # target tidak valid
    assert api.post("/api/workspaces/main/copy", json={"image_ids": [img]}).status_code == 400          # workspace yang sama
    api.post(f"/api/workspaces/{c}/archive")
    assert api.post(f"/api/workspaces/{c}/copy", json={"image_ids": [img]}).status_code == 404          # diarsip
    assert api.post(f"/api/workspaces/{b}/copy", json={}).status_code == 400                            # kosong
    assert api.post(f"/api/workspaces/{b}/copy", json={"image_ids": ["tidak-ada"]}).status_code == 404


def test_copy_skips_deleted_sheet_images_and_rejects_deleted_source(api):
    b = mkws(api, "B")
    cid, src = char(api)
    gone = up(api)
    api.studio.add_character_image(cid, gone, "side")
    api.studio.db.update("images", gone, {"deleted_at": "2026-01-01T00:00:00+00:00"})   # terhapus (soft)
    r = api.post(f"/api/workspaces/{b}/copy", json={"character_ids": [cid]}).json()
    assert len(r["images"]) == 1                                                        # hanya gambar sumber
    api.studio.db.update("images", src, {"deleted_at": "2026-01-01T00:00:00+00:00"})
    bad = api.post(f"/api/workspaces/{b}/copy", json={"character_ids": [cid]})
    assert bad.status_code == 409 and "sudah dihapus" in bad.json()["detail"]


def test_copied_character_works_in_target_workspace(api, fake):
    b = mkws(api, "B")
    cid, src = char(api)
    api.studio.add_character_image(cid, up(api), "front")
    copied = api.post(f"/api/workspaces/{b}/copy", json={"character_ids": [cid]}).json()
    new_char = copied["characters"][0]["to"]
    in_b = {i["id"]: i for i in api.get("/api/images", **hdr(b)).json()}
    base = next(i for i in in_b.values() if i["origin_image_id"] == src)["id"]
    r = api.post(f"/api/images/{base}/edit", json={"prompt": "x", "model": EDIT_MODEL, "character_id": new_char}, **hdr(b))
    assert r.status_code == 200, r.text
    assert api.post(f"/api/images/{base}/edit", json={"prompt": "x", "model": EDIT_MODEL, "character_id": cid}, **hdr(b)).status_code == 404
