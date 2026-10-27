import json

import pytest

from app import blockout
from app.service import ServiceError
from conftest import make_video
from test_scene_generate import estimate, ready_scene
from test_scenes import put
from test_workspaces import char, hdr, mkws, up

ACTOR = lambda cid, **k: {"character_id": cid, "keys": [{"t": 0, "pos": [0, 0, 0], "facing": 0, "pose": "stand"}], **k}
LAYOUT = lambda cid: {"version": 1, "duration": 4,
                      "camera": {"keys": [{"t": 0, "pos": [0, 1.6, 6], "target": [0, 1.2, 0], "mm": 35}]},
                      "actors": [ACTOR(cid)], "props": [{"type": "box", "pos": [2, 0.5, 0], "scale": [1, 1, 1]}]}


def first_scene(api):
    f = api.get("/api/films").json()[0]["id"]
    return api.get(f"/api/films/{f}").json()["scenes"][0]


# ---------- validasi murni ----------
def test_clean_normalizes_sorts_and_merges_duplicate_times():
    raw = LAYOUT("c1")
    raw["actors"][0]["keys"] = [{"t": 3, "pos": [1, 0, 0], "pose": "walk"}, {"t": 0, "pos": [0, 0, 0]}, {"t": 3, "pos": [2, 0, 0], "pose": "run"}]
    out = blockout.clean(raw, ["c1"])
    assert [(k["t"], k["pose"], k["pos"][0]) for k in out["actors"][0]["keys"]] == [(0.0, "stand", 0.0), (3.0, "run", 2.0)]
    assert out["props"][0]["color"] == "#8a8a8a" and out["version"] == 2 and out["props"][0]["id"] == "p1"


@pytest.mark.parametrize("mutate,msg", [
    (lambda r: r["actors"].append(ACTOR("c1")), "satu pemeran"),
    (lambda r: r["actors"].append(ACTOR("asing")), "pemeran adegan"),
    (lambda r: r["actors"][0]["keys"][0].update(pose="terbang"), "pose tidak dikenal"),
    (lambda r: r["actors"][0]["keys"][0].update(joints={"ekor": [0, 0, 0]}), "sendi tidak dikenal"),
    (lambda r: r["actors"][0]["keys"][0].update(pos=[0, 0, float("inf")]), "angka"),
    (lambda r: r["camera"]["keys"][0].update(mm=500), "camera.mm"),
    (lambda r: r["camera"]["keys"][0].update(t=99), "camera.t"),
    (lambda r: r["camera"].update(keys=[]), "minimal satu key"),
    (lambda r: r["props"][0].update(type="kapal"), "properti"),
    (lambda r: r["props"][0].update(color="merah"), "warna"),
    (lambda r: r.update(props=[LAYOUT("c1")["props"][0]] * 121), "maksimal 120"),
    (lambda r: r.update(duration=99), "duration"),
])
def test_clean_rejects(mutate, msg):
    raw = LAYOUT("c1")
    mutate(raw)
    with pytest.raises(ServiceError) as exc:
        blockout.clean(raw, ["c1"])
    assert exc.value.status == 422 and msg in str(exc.value)


# ---------- simpan lewat API ----------
def test_save_roundtrip_and_stale_actor_rejected(api):
    _, s, (cid,) = ready_scene(api)
    r = put(api, s, blockout=LAYOUT(cid))
    assert r.status_code == 200 and r.json()["blockout"]["actors"][0]["character_id"] == cid
    assert first_scene(api)["blockout"]["duration"] == 4
    other = char(api, name="Lain")[0]
    assert put(api, s, blockout=LAYOUT(other)).status_code == 422          # bukan pemeran adegan
    assert put(api, s, blockout=None).json()["blockout"] is None            # dikosongkan


def test_duplicate_copies_blockout(api):
    _, s, (cid,) = ready_scene(api)
    put(api, s, blockout=LAYOUT(cid))
    assert api.post(f"/api/scenes/{s}/duplicate").json()["blockout"]["duration"] == 4


def test_blockout_image_is_validated_and_cleared_when_image_deleted(api):
    _, s, _ = ready_scene(api)
    assert put(api, s, blockout_image_id="tidak-ada").status_code == 404
    img = up(api)
    assert put(api, s, blockout_image_id=img).json()["blockout_image_id"] == img
    assert api.delete(f"/api/images/{img}").status_code == 200
    assert first_scene(api)["blockout_image_id"] is None


def test_other_workspace_gets_404(api):
    _, s, (cid,) = ready_scene(api)
    ws = mkws(api, "lain")
    assert api.put(f"/api/scenes/{s}", json={"blockout": LAYOUT(cid)}, **hdr(ws)).status_code == 404
    assert api.raw.post(f"/api/scenes/{s}/blockout", json={"confirmed_cost": 1}, **hdr(ws)).status_code == 404
    assert api.post(f"/api/scenes/{s}/previs", files={"file": ("p.mp4", b"x", "video/mp4")}, **hdr(ws)).status_code == 404


# ---------- AI penyusun ----------
def generate(api, s, **kw):
    est = estimate(api, kind="scene_blockout", model="-", scene_id=s)
    return api.raw.post(f"/api/scenes/{s}/blockout", json={"confirmed_cost": est["high"], **kw})


def chat_calls(fake):
    return [r for r in fake.requests if r.url.path.endswith("/chat/completions")]


def test_generate_requires_confirmation_and_estimate_is_small(api, fake):
    _, s, _ = ready_scene(api)
    est = estimate(api, kind="scene_blockout", model="-", scene_id=s)
    assert 0 < est["high"] < 0.01 and est["confidence"] == "formula"
    assert api.raw.post(f"/api/scenes/{s}/blockout", json={}).status_code == 409
    assert not chat_calls(fake)


def test_generate_returns_draft_without_saving_and_counts_cost(api, fake):
    _, s, (cid,) = ready_scene(api)
    fake.chat_content = "```json\n" + json.dumps({**LAYOUT(cid), "duration": 99,
                                                  "actors": [ACTOR(cid), ACTOR("hantu"), ACTOR(cid)]}) + "\n```"
    before = api.studio.db.committed_today()
    r = generate(api, s)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [a["character_id"] for a in body["layout"]["actors"]] == [cid]     # aktor asing dan ganda dibuang
    assert body["layout"]["duration"] == 5                                     # durasi dipaksa mengikuti adegan, bukan AI
    assert first_scene(api)["blockout"] is None                                # draf belum disimpan
    assert api.studio.db.committed_today() == pytest.approx(before + 0.002)
    sent = json.loads(chat_calls(fake)[-1].content)
    assert sent["model"] == "anthropic/claude-haiku-5.5" and "aksi 0" in sent["messages"][1]["content"]


def test_unreadable_answer_is_502_but_cost_is_still_recorded(api, fake):
    _, s, _ = ready_scene(api)
    fake.chat_content = "bukan json"
    before = api.studio.db.committed_today()
    assert generate(api, s).status_code == 502
    assert api.studio.db.committed_today() > before


def test_invalid_layout_from_ai_is_502(api, fake):
    _, s, (cid,) = ready_scene(api)
    bad = LAYOUT(cid)
    bad["actors"][0]["keys"][0]["pose"] = "terbang"
    fake.chat_content = json.dumps(bad)
    r = generate(api, s)
    assert r.status_code == 502 and "pose" in r.json()["detail"]


def test_missing_cost_falls_back_to_estimate(api, fake):
    _, s, (cid,) = ready_scene(api)
    fake.chat_content, fake.chat_cost = json.dumps(LAYOUT(cid)), None
    assert generate(api, s).status_code == 200
    row = api.studio.db.one("SELECT cost, estimated_cost FROM text_jobs")
    assert row["cost"] is None and row["estimated_cost"] > 0


def test_daily_budget_blocks_generation(api, fake):
    _, s, _ = ready_scene(api)
    api.studio.s = type(api.studio.s)(**{**api.studio.s.__dict__, "daily_budget_usd": 0.0001})
    assert generate(api, s).status_code == 402
    assert not chat_calls(fake)


# ---------- previs ----------
def previs_file(tmp_path, color):
    return make_video(tmp_path / f"{color}.mp4", color=color, seconds=1).read_bytes()


def test_previs_upload_attaches_and_replaces_old_one(api, tmp_path):
    _, s, _ = ready_scene(api)
    first = api.post(f"/api/scenes/{s}/previs", files={"file": ("p.mp4", previs_file(tmp_path, "red"), "video/mp4")})
    assert first.status_code == 200, first.text
    ref1 = first.json()["previs_ref_id"]
    path1 = api.studio.db.one("SELECT path FROM refs WHERE id = ?", (ref1,))["path"]
    second = api.post(f"/api/scenes/{s}/previs", files={"file": ("p.mp4", previs_file(tmp_path, "blue"), "video/mp4")})
    ref2 = second.json()["previs_ref_id"]
    assert ref2 != ref1
    assert api.studio.db.one("SELECT 1 FROM refs WHERE id = ?", (ref1,)) is None       # previs lama dibersihkan
    assert not api.studio.storage.resolve(path1).exists()
    assert api.get(f"/api/references/{ref2}/file").status_code == 200


def test_previs_that_a_clip_uses_is_kept(api, tmp_path):
    _, s, _ = ready_scene(api)
    ref1 = api.post(f"/api/scenes/{s}/previs", files={"file": ("p.mp4", previs_file(tmp_path, "red"), "video/mp4")}).json()["previs_ref_id"]
    api.studio.db.execute("INSERT INTO clips (id, model, prompt, params, status, created_at, updated_at, workspace_id, reference_id, "
                          "chain_depth, kind) VALUES ('c', 'm', 'p', '{}', 'completed', 'x', 'x', 'main', ?, 0, 'motion')", (ref1,))
    api.post(f"/api/scenes/{s}/previs", files={"file": ("p.mp4", previs_file(tmp_path, "blue"), "video/mp4")})
    assert api.studio.db.one("SELECT 1 FROM refs WHERE id = ?", (ref1,))


def test_previs_accepts_streamed_webm_without_duration_header(api):
    """WebM dari MediaRecorder browser: ffprobe melaporkan duration=N/A (temuan nyata saat implementasi plan 14)."""
    import subprocess
    webm = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=320x180:d=2:r=24", "-c:v", "libvpx-vp9",
                           "-deadline", "realtime", "-f", "webm", "pipe:1"], check=True, capture_output=True).stdout
    _, s, _ = ready_scene(api)
    r = api.post(f"/api/scenes/{s}/previs", files={"file": ("previs.webm", webm, "video/webm")})
    assert r.status_code == 200, r.text
    ref = api.studio.db.one("SELECT duration, path FROM refs WHERE id = ?", (r.json()["previs_ref_id"],))
    assert ref["duration"] == pytest.approx(2.0, abs=0.2) and ref["path"].endswith(".mp4")


def test_previs_rejects_non_video(api):
    _, s, _ = ready_scene(api)
    assert api.post(f"/api/scenes/{s}/previs", files={"file": ("p.mp4", b"bukan video", "video/mp4")}).status_code == 415


def test_fresh_database_is_latest_with_blockout_columns(tmp_path):
    from app.db import Database
    db = Database(tmp_path / "x.db")
    cols = {r["name"] for r in db._conn.execute("PRAGMA table_info(scenes)")}
    assert {"blockout", "blockout_image_id", "previs_ref_id"} <= cols
    assert db._conn.execute("PRAGMA user_version").fetchone()[0] == 18
    assert db.one("SELECT COUNT(*) AS n FROM text_jobs")["n"] == 0
