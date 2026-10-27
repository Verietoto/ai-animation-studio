"""Plan 18 fase B (suara karakter) dan fase C bagian non-AI (beat adegan, versi, pemulihan)."""
import subprocess
from pathlib import Path

import pytest

from app import beats as beats_mod
from app.service import ServiceError
from conftest import png_bytes
from test_scenes import film, put, scene
from test_workspace_delete import archive
from test_workspaces import char, hdr, mkws, up


def sine(tmp_path: Path, seconds: float, name="s.wav") -> Path:
    out = tmp_path / name
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=330:d={seconds}", str(out)], check=True)
    return out


def add_voice(api, cid, ws=None, file: Path | None = None, **form):
    files = {"file": (file.name, file.read_bytes(), "audio/wav")} if file else None
    return api.post(f"/api/characters/{cid}/voices", data={k: str(v) for k, v in form.items()}, files=files, **(hdr(ws) if ws else {}))


# ---------- suara ----------
def test_text_only_voice_becomes_active_and_needs_description(api):
    cid, _ = char(api)
    assert add_voice(api, cid).status_code == 422
    r = add_voice(api, cid, description="suara berat dan serak")
    assert r.status_code == 200 and r.json()["has_audio"] is False and r.json()["source"] == "text" and r.json()["active"] is True
    got = api.get(f"/api/characters/{cid}/voices").json()
    assert got["active"] == r.json()["id"] and len(got["versions"]) == 1
    assert api.get(f"/api/voices/{r.json()['id']}/file").status_code == 404   # tanpa sampel


def test_upload_requires_consent_valid_audio_and_min_length(api, tmp_path):
    cid, _ = char(api)
    wav = sine(tmp_path, 3)
    assert add_voice(api, cid, file=wav, description="x").status_code == 422             # tanpa persetujuan
    assert add_voice(api, cid, file=sine(tmp_path, 1, "short.wav"), consent="true").status_code == 422
    junk = tmp_path / "bukan.wav"
    junk.write_bytes(png_bytes())
    assert add_voice(api, cid, file=junk, consent="true").status_code == 415
    ok = add_voice(api, cid, file=wav, consent="true", description="ceria", note="rekaman pertama")
    assert ok.status_code == 200
    v = ok.json()
    assert v["has_audio"] and v["source"] == "upload" and v["consent"] and 2.5 < v["duration"] < 3.5 and v["revision_note"] == "rekaman pertama"
    r = api.get(f"/api/voices/{v['id']}/file")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mp4" and len(r.content) > 500
    assert len(list(api.studio.storage.root.glob("*.upload"))) == 0                       # berkas sementara selalu dibersihkan


def test_long_upload_is_trimmed_to_max(api, tmp_path):
    cid, _ = char(api)
    v = add_voice(api, cid, file=sine(tmp_path, 20), consent="true").json()
    assert 14.5 < v["duration"] <= 15.2


def test_versions_activate_and_delete_fall_back_to_latest(api):
    cid, _ = char(api)
    a = add_voice(api, cid, description="satu").json()["id"]
    b = add_voice(api, cid, description="dua").json()["id"]
    c = add_voice(api, cid, description="tiga").json()["id"]
    assert api.get(f"/api/characters/{cid}/voices").json()["active"] == c
    assert api.post(f"/api/voices/{a}/activate").json()["active"] is True
    assert api.get(f"/api/characters/{cid}/voices").json()["active"] == a
    assert api.delete(f"/api/voices/{a}").status_code == 200                                # yang aktif dihapus -> versi terbaru tersisa
    assert api.get(f"/api/characters/{cid}/voices").json()["active"] == c
    api.delete(f"/api/voices/{c}")
    api.delete(f"/api/voices/{b}")
    got = api.get(f"/api/characters/{cid}/voices").json()
    assert got["active"] is None and got["versions"] == []
    assert api.delete(f"/api/voices/{b}").status_code == 404


def test_voice_is_workspace_scoped_and_removed_with_character(api, tmp_path):
    b = mkws(api, "B")
    cid, _ = char(api, b)
    vid = add_voice(api, cid, ws=b, file=sine(tmp_path, 3), consent="true").json()["id"]
    assert api.get(f"/api/characters/{cid}/voices").status_code == 404                     # header Utama
    assert api.post(f"/api/voices/{vid}/activate").status_code == 404
    assert api.delete(f"/api/voices/{vid}").status_code == 404
    path = Path(api.studio.db.one("SELECT path FROM voice_versions WHERE id = ?", (vid,))["path"])
    assert path.is_file()
    assert api.delete(f"/api/characters/{cid}", **hdr(b)).status_code == 200
    assert api.studio.db.one("SELECT COUNT(*) AS n FROM voice_versions")["n"] == 0 and not path.exists()


def test_workspace_copy_copies_active_voice_only(api, tmp_path):
    cid, img = char(api)
    add_voice(api, cid, file=sine(tmp_path, 3), consent="true", description="lama")
    add_voice(api, cid, description="aktif, hanya teks")
    b = mkws(api, "B")
    r = api.post(f"/api/workspaces/{b}/copy", json={"image_ids": [], "character_ids": [cid]})
    assert r.status_code == 200, r.text
    new = r.json()["characters"][0]["to"]
    got = api.get(f"/api/characters/{new}/voices", **hdr(b)).json()
    assert len(got["versions"]) == 1 and got["versions"][0]["description"] == "aktif, hanya teks" and got["active"] == got["versions"][0]["id"]
    assert len(api.get(f"/api/characters/{cid}/voices").json()["versions"]) == 2          # asal tidak berubah


def test_workspace_delete_removes_voices_and_beats(api, tmp_path):
    b = mkws(api, "B")
    cid, _ = char(api, b)
    vid = add_voice(api, cid, ws=b, file=sine(tmp_path, 3), consent="true").json()["id"]
    path = Path(api.studio.db.one("SELECT path FROM voice_versions WHERE id = ?", (vid,))["path"])
    f = film(api, b)
    sid = scene(api, f, b)["id"]
    assert api.put(f"/api/scenes/{sid}/beats", json={"beats": [{"start": 0, "end": 4}]}, **hdr(b)).status_code == 200
    archive(api, b)
    assert api.delete(f"/api/workspaces/{b}").status_code == 200
    db = api.studio.db
    assert db.one("SELECT COUNT(*) AS n FROM voice_versions")["n"] == 0 and not path.exists()
    assert db.one("SELECT COUNT(*) AS n FROM scene_beats")["n"] == 0 and db.one("SELECT COUNT(*) AS n FROM beat_versions")["n"] == 0


# ---------- beat: aturan murni ----------
def beat(start, end, **kw):
    return {"start": start, "end": end, **kw}


def test_clean_requires_contiguous_beats_from_zero_with_min_length():
    ok, w = beats_mod.clean([beat(0, 3), beat(3, 6.5), beat(6.5, 9)], set(), 9)
    assert [(b["start"], b["end"]) for b in ok] == [(0, 3), (3, 6.5), (6.5, 9)] and len(w) == 1 and "1-3 dtk" in w[0]
    for bad in ([beat(1, 3)], [beat(0, 3), beat(4, 6)], [beat(0, 3), beat(2, 6)], [beat(0, 0.5)], [beat(0, "x")], []):
        with pytest.raises(ServiceError):
            beats_mod.clean(bad, set())


def test_clean_rounds_snaps_and_warns_about_total_and_dense_dialogue():
    ok, w = beats_mod.clean([beat(0.04, 3.04), beat(3.0, 6)], {"a"}, 10)
    assert (ok[0]["start"], ok[1]["start"]) == (0, 3.0) and any("durasi adegan 10" in x for x in w)
    dense = {"character_id": "a", "text": "satu dua tiga empat lima enam tujuh delapan"}
    _, w = beats_mod.clean([beat(0, 2, cast=["a"], dialogue=[dense])], {"a"}, 2)
    assert any("terlalu padat" in x for x in w)


def test_clean_checks_cast_and_speakers_and_lenient_mode_drops_unknown():
    with pytest.raises(ServiceError):
        beats_mod.clean([beat(0, 3, cast=["x"])], {"a"})
    with pytest.raises(ServiceError):
        beats_mod.clean([beat(0, 3, dialogue=[{"character_id": "x", "text": "hai"}])], {"a"})
    ok, w = beats_mod.clean([beat(0, 3, cast=["a", "x"], dialogue=[{"character_id": "x", "text": "hai"}, {"character_id": "a", "text": "yo"}])],
                            {"a"}, strict=False)
    assert ok[0]["cast"] == ["a"] and [d["text"] for d in ok[0]["dialogue"]] == ["yo"] and len(w) == 2
    with pytest.raises(ServiceError):
        beats_mod.clean([beat(0, 3, action="x" * 301)], set())
    ok, _ = beats_mod.clean([beat(0, 3, dialogue=[{"character_id": "a", "text": "   "}])], {"a"})   # dialog kosong dibuang
    assert ok[0]["dialogue"] == []


# ---------- beat: penyimpanan ----------
def setup_scene(api, ws=None):
    f = film(api, ws)
    cid, _ = char(api, ws)
    s = scene(api, f, ws)
    put(api, s["id"], ws, planned_seconds=9, cast=[{"character_id": cid, "action": "melompat"}])
    return s["id"], cid


def test_replace_list_and_snapshot_versions(api):
    sid, cid = setup_scene(api)
    assert api.get(f"/api/scenes/{sid}/beats").json()["beats"] == []
    first = api.put(f"/api/scenes/{sid}/beats", json={"beats": [beat(0, 4, action="masuk", cast=[cid]), beat(4, 9, action="duduk")], "note": "awal"})
    assert first.status_code == 200, first.text
    got = first.json()
    assert [(b["start"], b["end"], b["action"]) for b in got["beats"]] == [(0, 4, "masuk"), (4, 9, "duduk")] and got["warnings"] == []
    assert api.get(f"/api/scenes/{sid}/beats/versions").json() == []                       # belum ada susunan lama untuk dipotret
    second = api.put(f"/api/scenes/{sid}/beats", json={"beats": [beat(0, 9, action="semua")], "note": "ringkas"}).json()
    assert len(second["beats"]) == 1
    versions = api.get(f"/api/scenes/{sid}/beats/versions").json()
    assert len(versions) == 1 and versions[0]["count"] == 2 and versions[0]["note"] == "ringkas" and versions[0]["seconds"] == 9
    back = api.post(f"/api/scenes/{sid}/beats/restore", json={"version_id": versions[0]["id"]}).json()
    assert [b["action"] for b in back["beats"]] == ["masuk", "duduk"]
    assert len(api.get(f"/api/scenes/{sid}/beats/versions").json()) == 2                    # pemulihan juga dipotret (bisa dibatalkan)
    assert api.post(f"/api/scenes/{sid}/beats/restore", json={"version_id": "nope"}).status_code == 404


def test_image_is_kept_by_beat_id_and_never_taken_from_client(api):
    sid, _ = setup_scene(api)
    first = api.put(f"/api/scenes/{sid}/beats", json={"beats": [beat(0, 9)]}).json()["beats"][0]
    img = up(api)
    api.studio.db.execute("UPDATE scene_beats SET image_id = ? WHERE id = ?", (img, first["id"]))
    again = api.put(f"/api/scenes/{sid}/beats", json={"beats": [{**beat(0, 5), "id": first["id"]}, beat(5, 9, image_id=img)]}).json()["beats"]
    assert again[0]["id"] == first["id"] and again[0]["image_id"] == img                    # diwarisi dari beat lama
    assert again[1]["image_id"] is None                                                    # klien tidak bisa memasang gambar ke beat baru
    other = api.put(f"/api/scenes/{sid}/beats", json={"beats": [{**beat(0, 9), "id": "buatan-klien"}]}).json()["beats"][0]
    assert other["id"] != "buatan-klien" and other["image_id"] is None


def test_beat_ids_are_not_hijackable_across_scenes_and_workspaces(api):
    sid, _ = setup_scene(api)
    mine = api.put(f"/api/scenes/{sid}/beats", json={"beats": [beat(0, 9)]}).json()["beats"][0]["id"]
    b = mkws(api, "B")
    other, _ = setup_scene(api, b)
    got = api.put(f"/api/scenes/{other}/beats", json={"beats": [{**beat(0, 9), "id": mine}]}, **hdr(b))
    assert got.status_code == 200 and got.json()["beats"][0]["id"] != mine
    assert api.get(f"/api/scenes/{sid}/beats", **hdr(b)).status_code == 404                  # adegan Utama dari workspace B
    assert api.put(f"/api/scenes/{sid}/beats", json={"beats": [beat(0, 9)]}, **hdr(b)).status_code == 404


def test_broken_beats_are_flagged_not_deleted_when_cast_changes(api):
    sid, cid = setup_scene(api)
    api.put(f"/api/scenes/{sid}/beats", json={"beats": [beat(0, 9, cast=[cid], dialogue=[{"character_id": cid, "text": "hai"}])]})
    put(api, sid, cast=[])
    got = api.get(f"/api/scenes/{sid}/beats").json()
    assert got["beats"][0]["broken"] is True and any("dilepas" in w for w in got["warnings"]) and got["beats"][0]["cast"] == [cid]
    assert api.put(f"/api/scenes/{sid}/beats", json={"beats": [beat(0, 9, cast=[cid])]}).status_code == 422   # menyimpan ulang butuh perbaikan


def test_versions_are_capped_and_scene_delete_cleans_up(api):
    sid, _ = setup_scene(api)
    for n in range(beats_mod.VERSIONS_MAX + 5):
        assert api.put(f"/api/scenes/{sid}/beats", json={"beats": [beat(0, 2 + (n % 5))], "note": f"v{n}"}).status_code == 200
    assert len(api.get(f"/api/scenes/{sid}/beats/versions").json()) == beats_mod.VERSIONS_MAX
    assert api.delete(f"/api/scenes/{sid}").status_code == 200
    db = api.studio.db
    assert db.one("SELECT COUNT(*) AS n FROM scene_beats")["n"] == 0 and db.one("SELECT COUNT(*) AS n FROM beat_versions")["n"] == 0


def test_rendering_episode_blocks_beat_edits(api):
    sid, _ = setup_scene(api)
    fid = api.studio.db.one("SELECT film_id FROM scenes WHERE id = ?", (sid,))["film_id"]
    api.studio.db.execute("UPDATE films SET render_status = 'rendering' WHERE id = ?", (fid,))
    assert api.put(f"/api/scenes/{sid}/beats", json={"beats": [beat(0, 9)]}).status_code == 409
