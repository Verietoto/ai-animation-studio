"""Plan 18 fase A: pengaturan proyek (= workspace), rasio satu sumber, penguncian, dan authorize tanpa batas untuk v2."""
import time

import pytest

from app import pricing
from app.db import Database
from app.service import ServiceError
from conftest import upload

ID = "main"
SEEDANCE = {"id": "bytedance/seedance-2.0-mini", "supported_durations": [4, 8], "supported_resolutions": ["480p", "720p"],
            "supported_aspect_ratios": ["16:9", "9:16"], "supported_frame_images": ["first_frame"], "generate_audio": True}


def with_seedance(api):
    """Katalog fake hanya punya seedance-2.5; suntik model keluarga 2.0 lewat cache katalog."""
    api.studio._models = (time.time(), [*api.studio.video_models(), SEEDANCE, {**SEEDANCE, "id": "bytedance/seedance-2.0-fast"}])


def put(api, ws=ID, **body):
    return api.put(f"/api/workspaces/{ws}/settings", json=body)


def settings(api, ws=ID):
    return api.get(f"/api/workspaces/{ws}/settings").json()


def test_defaults_and_roundtrip(api):
    with_seedance(api)
    s = settings(api)
    assert (s["video_model"], s["video_resolution"], s["aspect_ratio"], s["generate_audio"]) == ("bytedance/seedance-2.0", "720p", "16:9", True)
    assert s["ratio_locked"] is False and s["image_model"] is None and s["style"] == ""
    assert s["allowed_video_models"] == ["bytedance/seedance-2.0", "bytedance/seedance-2.0-fast", "bytedance/seedance-2.0-mini", "heygen/heygen-video-1"]
    assert s["model_caps"]["heygen/heygen-video-1"]["previs"] is False and s["model_caps"]["bytedance/seedance-2.0"]["previs"] is True
    got = put(api, video_model="bytedance/seedance-2.0-fast", generate_audio=False, style="kartun 2D").json()
    assert got["video_model"] == "bytedance/seedance-2.0-fast" and got["generate_audio"] is False and got["style"] == "kartun 2D"
    assert settings(api)["style"] == "kartun 2D"


def test_video_model_is_locked_to_seedance_2_family(api):
    with_seedance(api)
    for other in ("bytedance/seedance-2.5", "kwaivgi/kling-v3.0-std", "x/tidak-ada"):          # ada di katalog atau tidak: tetap ditolak
        r = put(api, video_model=other)
        assert r.status_code == 422 and "Seedance 2.0" in r.json()["detail"], other
    assert settings(api)["video_model"] == "bytedance/seedance-2.0"
    assert put(api, video_model="bytedance/seedance-2.0-mini").status_code == 200


def test_validation(api):
    with_seedance(api)
    assert put(api, video_resolution="999p").status_code == 422
    assert put(api, video_model="bytedance/seedance-2.0-mini", video_resolution="1080p").status_code == 422   # mini hanya 480p/720p
    assert put(api, video_model="bytedance/seedance-2.0-mini", video_resolution="480p").status_code == 200
    assert put(api, aspect_ratio="lebar").status_code == 422
    assert put(api, image_model="x/tidak-ada").status_code == 422
    assert put(api, style="x" * 501).status_code == 422
    assert put(api, ws="nope", style="a").status_code == 404
    assert settings(api)["style"] == ""                                                         # penolakan tidak menyimpan apa pun


def test_ratio_syncs_films_and_asks_confirmation_when_assets_exist(api):
    a = api.post("/api/films", json={"title": "A"}).json()["id"]
    b = api.post("/api/films", json={"title": "B"}).json()["id"]
    api.put(f"/api/films/{b}", json={"aspect_ratio": "9:16"})
    assert settings(api)["mismatched_films"] == 1
    got = put(api, aspect_ratio="9:16")
    assert got.status_code == 200 and got.json()["synced_films"] == 1
    assert {api.get(f"/api/films/{i}").json()["aspect_ratio"] for i in (a, b)} == {"9:16"}
    # episode yang sudah punya keyframe pada rasio lain: perlu confirm_sync
    img = upload(api)["id"]
    api.studio.db.execute("INSERT INTO scenes (id, film_id, position, keyframe_image_id, created_at, updated_at) "
                          "VALUES ('s1', ?, 0, ?, 't', 't')", (a, img))
    r = put(api, aspect_ratio="1:1")
    assert r.status_code == 409 and r.json()["films_with_assets"] == 1
    assert settings(api)["aspect_ratio"] == "9:16"                       # ditolak = tidak berubah
    ok = put(api, aspect_ratio="1:1", confirm_sync=True)
    assert ok.status_code == 200 and ok.json()["aspect_ratio"] == "1:1"
    assert api.get(f"/api/films/{b}").json()["aspect_ratio"] == "1:1"


def test_ratio_locked_by_v2_assets(api):
    img = upload(api)["id"]
    api.studio.db.execute("UPDATE images SET beat_id = 'b1' WHERE id = ?", (img,))
    s = settings(api)
    assert s["ratio_locked"] is True and s["v2_assets"]["beat_images"] == 1
    r = put(api, aspect_ratio="9:16")
    assert r.status_code == 409 and "terkunci" in r.json()["detail"]
    assert put(api, aspect_ratio="16:9", style="ok").status_code == 200   # rasio sama = tidak dianggap perubahan


def test_settings_are_per_workspace(api):
    other = api.post("/api/workspaces", json={"name": "Proyek B"}).json()["id"]
    put(api, ws=other, aspect_ratio="9:16")
    assert settings(api)["aspect_ratio"] == "16:9"
    assert settings(api, other)["aspect_ratio"] == "9:16"


def test_migration_v14_backfills_ratio_from_most_common_film_ratio(tmp_path):
    db = Database(tmp_path / "old.db")
    for i, ratio in enumerate(["16:9", "9:16", "9:16"]):
        db.execute("INSERT INTO films (id, title, aspect_ratio, workspace_id, created_at, updated_at) VALUES (?, 't', ?, 'main', ?, ?)",
                   (f"f{i}", ratio, f"2026-01-0{i + 1}", f"2026-01-0{i + 1}"))
    db._conn.execute("UPDATE workspaces SET aspect_ratio = '16:9'")
    db._conn.execute("PRAGMA user_version = 13")
    db._conn.commit()
    db2 = Database(tmp_path / "old.db")
    assert db2.one("SELECT aspect_ratio FROM workspaces WHERE id = 'main'")["aspect_ratio"] == "9:16"
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] == 20


def test_authorize_limits_false_skips_job_and_daily_limits_but_keeps_confirmation(api):
    st = api.studio
    est = pricing.Estimate(low=5.0, high=5.0, confidence="exact")
    with pytest.raises(ServiceError) as e:
        st.authorize(est, 5.0, False)                      # jalur lama: terblokir batas per job
    assert e.value.status == 402
    st.authorize(est, 5.0, False, limits=False)            # v2: lolos
    with pytest.raises(ServiceError) as e:
        st.authorize(est, None, False, limits=False)       # konfirmasi tetap wajib
    assert e.value.status == 409
    with pytest.raises(ServiceError) as e:
        st.authorize(est, 1.0, False, limits=False)        # dan harus cocok dengan estimasi
    assert e.value.status == 409
