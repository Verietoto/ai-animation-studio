import sqlite3
import threading

from conftest import upload

CLIP = {"model": "bytedance/seedance-2.5", "prompt": "zoom", "duration": 4, "resolution": "720p", "aspect_ratio": "16:9"}


def post_clip(api, img, **extra):
    return api.raw.post("/api/clips", json={**CLIP, "image_id": img["id"], **extra})


def test_generate_without_confirmation_is_rejected_and_never_reaches_provider(api, fake):
    img = upload(api)
    r = post_clip(api, img)
    assert r.status_code == 409 and "confirmed_cost" in r.json()["detail"]
    assert r.json()["estimate"]["high"] == 0.2          # 0.05/s x 4s, ditampilkan agar UI bisa mengonfirmasi
    assert fake.submit_count == 0


def test_estimate_endpoint_has_no_side_effects_and_matches_charge(api, fake):
    img = upload(api)
    est = api.raw.post("/api/estimate", json={"kind": "video", "model": CLIP["model"], "duration": 4,
                                              "resolution": "720p", "aspect_ratio": "16:9"}).json()
    assert est["confidence"] == "exact" and est["high"] == 0.2 and est["blocked"] is None
    assert fake.submit_count == 0 and api.raw.get("/api/clips").json() == []
    ok = post_clip(api, img, confirmed_cost=est["high"])
    assert ok.status_code == 200
    assert api.studio.db.one("SELECT estimated_cost FROM clips")["estimated_cost"] == 0.2


def test_estimate_validates_parameters_like_generate(api):
    r = api.raw.post("/api/estimate", json={"kind": "video", "model": CLIP["model"], "duration": 99})
    assert r.status_code == 400


def test_confirmed_cost_lower_than_server_estimate_is_rejected(api, fake):
    img = upload(api)
    r = post_clip(api, img, confirmed_cost=0.05)
    assert r.status_code == 409 and "konfirmasi ulang" in r.json()["detail"]
    assert fake.submit_count == 0


def test_per_job_limit_enforced_server_side(api, fake, settings):
    img = upload(api)
    api.studio.s = type(settings)(**{**settings.__dict__, "max_cost_per_job": 0.1})
    r = post_clip(api, img, confirmed_cost=0.2)
    assert r.status_code == 402 and "per job" in r.json()["detail"]
    assert fake.submit_count == 0


def test_daily_limit_counts_active_jobs_not_only_finished_ones(api, fake, settings):
    img = upload(api)
    api.studio.s = type(settings)(**{**settings.__dict__, "daily_budget_usd": 0.3})
    assert post_clip(api, img, confirmed_cost=0.2).status_code == 200     # belum selesai, belum ada biaya aktual
    r = post_clip(api, img, confirmed_cost=0.2)                           # 0.2 terpesan + 0.2 > 0.3
    assert r.status_code == 402 and "batas harian" in r.json()["detail"]
    assert fake.submit_count == 1


def test_concurrent_requests_cannot_both_pass_the_budget_check(api, fake, settings):
    img = upload(api)
    api.studio.s = type(settings)(**{**settings.__dict__, "daily_budget_usd": 0.3})
    results = []

    def go():
        results.append(post_clip(api, img, confirmed_cost=0.2).status_code)

    threads = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [200, 402, 402, 402] and fake.submit_count == 1


def test_unknown_cost_needs_explicit_acceptance(api, fake):
    img = upload(api)
    fake.unpriced = True
    r = api.raw.post("/api/clips", json={"image_id": img["id"], "prompt": "x", "model": "x/unpriced"})
    assert r.status_code == 409 and "tidak diketahui" in r.json()["detail"]
    ok = api.raw.post("/api/clips", json={"image_id": img["id"], "prompt": "x", "model": "x/unpriced",
                                          "accept_unknown_cost": True})
    assert ok.status_code == 200 and fake.submit_count == 1


def test_actual_cost_replaces_estimate_in_budget_after_completion(api, fake):
    img = upload(api)
    c = post_clip(api, img, confirmed_cost=0.2).json()
    assert api.studio.db.committed_today() == 0.2                 # estimasi
    api.studio.poll_once()                                         # biaya aktual 0.4 dari provider palsu
    assert api.get(f"/api/clips/{c['id']}").json()["cost"] == 0.4
    assert api.studio.db.committed_today() == 0.4


def test_failed_job_without_cost_is_not_counted(api, fake):
    img = upload(api)
    c = post_clip(api, img, confirmed_cost=0.2).json()
    fake.video_status = "failed"
    api.studio.poll_once()
    assert api.studio.db.committed_today() in (0.0, 0.4)           # biaya nyata bila provider melaporkan, selain itu 0
    assert api.get(f"/api/clips/{c['id']}").json()["status"] == "failed"


def test_extend_rejection_leaves_no_orphan_frame(api, fake, settings):
    img = upload(api)
    c1 = post_clip(api, img, confirmed_cost=0.2).json()
    api.studio.poll_once()
    before = len(api.get("/api/images").json())
    r = api.raw.post(f"/api/clips/{c1['id']}/extend", json={"prompt": "lanjut", "model": CLIP["model"], "duration": 4})
    assert r.status_code == 409                                    # tanpa konfirmasi
    assert len(api.get("/api/images").json()) == before


def test_image_edit_token_priced_requires_confirmation_of_bound(api, fake):
    img = upload(api)
    r = api.raw.post(f"/api/images/{img['id']}/edit", json={"prompt": "x", "model": "openai/gpt-image-2"})
    assert r.status_code == 409 and r.json()["estimate"]["confidence"] in ("exact", "bound", "unknown")


def test_old_database_is_migrated(tmp_path):
    from app.db import Database
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE images (id TEXT PRIMARY KEY, parent_image_id TEXT, kind TEXT NOT NULL, prompt TEXT, model TEXT,
            path TEXT NOT NULL, width INTEGER, height INTEGER, cost REAL, created_at TEXT NOT NULL);
        CREATE TABLE clips (id TEXT PRIMARY KEY, parent_clip_id TEXT, source_image_id TEXT, prompt TEXT NOT NULL,
            model TEXT NOT NULL, params TEXT NOT NULL, status TEXT NOT NULL, remote_job_id TEXT, path TEXT,
            merged_path TEXT, cost REAL, error TEXT, chain_depth INTEGER NOT NULL DEFAULT 0, idempotency_key TEXT UNIQUE,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        INSERT INTO clips VALUES ('c1', NULL, NULL, 'p', 'm', '{}', 'completed', 'r', NULL, NULL, 0.5, NULL, 0, NULL, '2999-01-01', '2999-01-01');
    """)
    conn.commit(); conn.close()
    db = Database(path)
    row = db.one("SELECT id, cost, estimated_cost FROM clips")
    assert row == {"id": "c1", "cost": 0.5, "estimated_cost": None}
    assert db.one("PRAGMA user_version")["user_version"] == 4   # migrasi bertingkat sampai versi terbaru
    Database(path)   # idempotent: membuka lagi tidak error
