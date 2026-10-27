import json

import pytest

from app import script
from app.db import Database
from conftest import make_video
from test_scene_generate import estimate, ready_scene
from test_scenes import film, put, scene
from test_workspace_delete import archive
from test_workspaces import char, hdr, mkws, up


def jr(api, f, ws=None):
    r = api.get(f"/api/films/{f}/journey", **(hdr(ws) if ws else {}))
    assert r.status_code == 200, r.text
    return r.json()


def cast(api, f, chars=(), locs=(), ws=None, **kw):
    return api.put(f"/api/films/{f}/cast", json={"character_ids": list(chars), "location_ids": list(locs), **kw}, **(hdr(ws) if ws else {}))


def loc(api, name="Warung", ws=None):
    r = api.post("/api/locations", json={"name": name, "description": "kayu, temaram", "image_id": up(api, ws)}, **(hdr(ws) if ws else {}))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def first_film(api):
    return api.get("/api/films").json()[0]["id"]


# ---------- modul murni ----------
def test_mentions_analysis_rename_and_digest():
    text = "@[Rani] masuk ke #[Warung kopi]. @[rani] duduk; @[Budi] menyusul. #[Pasar]"
    assert script.mentions(text)[:2] == [("character", "Rani"), ("location", "Warung kopi")]
    out = script.analyze(text, [{"name": "Rani"}, {"name": "Rani"}], [{"name": "warung KOPI"}])
    assert out["ambiguous"] == [{"kind": "character", "name": "Rani"}]
    assert {(u["kind"], u["name"]) for u in out["unknown"]} == {("character", "Budi"), ("location", "Pasar")}
    assert script.rename(text, "location", "Warung Kopi", "Kedai").startswith("@[Rani] masuk ke #[Kedai]")
    assert script.rename("Warung kopi biasa", "location", "Warung kopi", "Kedai") == "Warung kopi biasa"   # teks biasa tidak disentuh
    assert script.rename("@[Warung]", "location", "Warung", "X") == "@[Warung]"                              # beda jenis tidak disentuh
    assert script.digest(" a ") == script.digest("a")


def test_clean_split_drops_foreign_ids_limits_cast_and_clamps():
    raw = [{"location_id": "L9", "planned_seconds": 999, "camera": "x" * 500, "cast": [
        {"character_id": "c1", "action": "a"}, {"character_id": "c1", "action": "dobel"}, {"character_id": "hantu"},
        {"character_id": "c2"}, {"character_id": "c3"}, {"character_id": "c4"}]}, "bukan objek", {"planned_seconds": "x"}]
    scenes, warnings = script.clean_split(raw, ["c1", "c2", "c3", "c4"], ["L1"])
    assert len(scenes) == 2 and scenes[0]["location_id"] is None and scenes[0]["planned_seconds"] == 120
    assert [c["character_id"] for c in scenes[0]["cast"]] == ["c1", "c2", "c3"] and len(scenes[0]["camera"]) == 120
    assert scenes[1]["planned_seconds"] == 5
    assert any("latar" in w for w in warnings) and any("di luar episode" in w for w in warnings) and any("pertama" in w for w in warnings)
    many, warn = script.clean_split([{}] * 60, [], [])
    assert len(many) == 50 and warn


# ---------- migrasi: isi awal dari adegan lama ----------
def test_migration_v12_backfills_cast_and_locations_from_existing_scenes(tmp_path):
    db = Database(tmp_path / "x.db")
    db.insert("films", {"id": "f1", "title": "E", "clip_ids": "[]", "render_status": "idle", "created_at": "t", "updated_at": "t",
                        "workspace_id": "main", "number": 1, "synopsis": "", "aspect_ratio": "16:9"})
    for pos, (sid, lid) in enumerate([("s1", "L1"), ("s2", "L2"), ("s3", "L1")]):
        db.insert("scenes", {"id": sid, "film_id": "f1", "position": pos, "location_id": lid, "created_at": "t", "updated_at": "t"})
    for sid, cid, pos in [("s1", "cB", 0), ("s1", "cA", 1), ("s2", "cA", 0), ("s3", "cC", 0)]:
        db.insert("scene_cast", {"scene_id": sid, "character_id": cid, "outfit_id": None, "action": "", "position": pos})
    db.execute("DELETE FROM film_characters")
    db.execute("DELETE FROM film_locations")
    db.execute("PRAGMA user_version = 11")
    for _ in range(2):   # dua kali: idempoten
        db2 = Database(tmp_path / "x.db")
        assert [r["character_id"] for r in db2.all("SELECT character_id FROM film_characters WHERE film_id = 'f1' ORDER BY position")] == ["cB", "cA", "cC"]
        assert [r["location_id"] for r in db2.all("SELECT location_id FROM film_locations WHERE film_id = 'f1' ORDER BY position")] == ["L1", "L2"]
        db2.execute("PRAGMA user_version = 11")


# ---------- pemeran & latar episode ----------
def test_set_cast_validations_and_state(api):
    f = film(api)
    a, b, l1 = char(api, name="Rani")[0], char(api, name="Budi")[0], loc(api)
    r = cast(api, f, [a, b], [l1])
    assert r.status_code == 200, r.text
    st = r.json()
    assert [c["name"] for c in st["characters"]] == ["Rani", "Budi"] and st["locations"][0]["name"] == "Warung"
    assert st["characters"][0]["has_sheet"] is False and st["progress"]["scenes"] == 0
    dup = char(api, name="rani")[0]
    r = cast(api, f, [a, dup])
    assert r.status_code == 422 and "bernama" in r.json()["detail"]                       # nama ganda di episode
    assert len(cast(api, f, [a, a]).json()["characters"]) == 1                              # id ganda dibuang
    assert cast(api, f, ["tidak-ada"]).status_code == 404
    assert cast(api, f, [a], ws=mkws(api, "lain")).status_code == 404                       # episode milik workspace lain
    assert cast(api, f, [a], locs=[loc(api, "X", mkws(api, "dua"))]).status_code == 404     # latar milik workspace lain


def test_names_with_brackets_are_refused(api):
    r = api.post("/api/characters", json={"name": "Ra[ni]", "description": "x", "source_image_id": up(api)})
    assert r.status_code == 422 and "[" in r.json()["detail"]
    assert api.post("/api/locations", json={"name": "Warung]", "image_id": up(api)}).status_code == 422


def test_removing_used_cast_is_refused_unless_released(api):
    _, s, (cid,) = ready_scene(api)
    f = first_film(api)
    assert [c["id"] for c in jr(api, f)["characters"]] == [cid]                              # otomatis masuk episode
    assert len(jr(api, f)["locations"]) == 1
    r = cast(api, f, [], [])
    assert r.status_code == 409 and "1" in r.json()["detail"]
    r = cast(api, f, [], [], release=True)
    assert r.status_code == 200 and r.json()["characters"] == []
    got = api.get(f"/api/films/{f}").json()["scenes"][0]
    assert got["cast"] == [] and got["location"] is None


def test_cast_added_to_scene_joins_episode_automatically(api):
    f = film(api)
    s = scene(api, f)["id"]
    cid, lid = char(api, name="Siti")[0], loc(api, "Pasar")
    put(api, s, cast=[{"character_id": cid, "action": "belanja"}], location_id=lid)
    st = jr(api, f)
    assert [c["id"] for c in st["characters"]] == [cid] and [l["id"] for l in st["locations"]] == [lid]


def test_deleting_character_location_film_and_workspace_cleans_episode_tables(api):
    f = film(api)
    a, l1 = char(api, name="Rani")[0], loc(api)
    cast(api, f, [a], [l1])
    api.delete(f"/api/characters/{a}")
    api.delete(f"/api/locations/{l1}")
    st = jr(api, f)
    assert st["characters"] == [] and st["locations"] == []
    assert api.studio.db.one("SELECT COUNT(*) AS n FROM film_characters")["n"] == 0
    assert api.studio.db.one("SELECT COUNT(*) AS n FROM film_locations")["n"] == 0
    b = char(api, name="Budi")[0]
    cast(api, f, [b])
    assert api.delete(f"/api/films/{f}").status_code == 200
    assert api.studio.db.one("SELECT COUNT(*) AS n FROM film_characters")["n"] == 0
    ws = mkws(api, "sementara")
    f2 = api.post("/api/films", json={"title": "E"}, **hdr(ws)).json()["id"]
    c2 = char(api, ws, name="Dewi")[0]
    assert cast(api, f2, [c2], ws=ws).status_code == 200
    archive(api, ws)
    assert api.delete(f"/api/workspaces/{ws}").status_code == 200
    assert api.studio.db.one("SELECT COUNT(*) AS n FROM film_characters")["n"] == 0


# ---------- naskah ----------
def test_script_saves_analyzes_mentions_and_limits_length(api):
    f = film(api)
    a = char(api, name="Rani")[0]
    cast(api, f, [a], [loc(api)])
    text = "@[Rani] masuk ke #[Warung]. @[Budi] menyusul."
    assert api.put(f"/api/films/{f}", json={"script": text}).status_code == 200
    st = jr(api, f)
    assert st["script"] == text and st["mentions"]["unknown"] == [{"kind": "character", "name": "Budi"}]
    assert st["script_changed"] is False
    assert api.put(f"/api/films/{f}", json={"script": "x" * 20_001}).status_code == 422


def test_renaming_location_rewrites_mentions_in_episode_scripts(api):
    f = film(api)
    l1 = loc(api, "Warung")
    cast(api, f, [], [l1])
    api.put(f"/api/films/{f}", json={"script": "Mereka ke #[Warung]. Warung itu ramai."})
    assert api.put(f"/api/locations/{l1}", json={"name": "Kedai"}).status_code == 200
    assert jr(api, f)["script"] == "Mereka ke #[Kedai]. Warung itu ramai."
    assert api.put(f"/api/locations/{l1}", json={"name": "Ke]dai"}).status_code == 422


# ---------- AI: naskah ----------
def chat_calls(fake):
    return [r for r in fake.requests if r.url.path.endswith("/chat/completions")]


FORMATTED_SCRIPT = """ADEGAN 1 — #[Warung]
FORMAT: 4s / 2 SHOTS / drama
SUBJECT: @[Rani], gadis desa
WARDROBE: Rani: kebaya biru
ENVIRONMENT: #[Warung], sore hari
MOOD: tenang
SHOT 1 — 0:00 to 0:02, WS, 24mm, locked. @[Rani] tiba di warung.
SHOT 2 — 0:02 to 0:04, MCU, 85mm, slow push-in. @[Rani] says: "Aku pulang"
"""


def test_script_draft_requires_synopsis_returns_draft_and_counts_cost(api, fake):
    f = film(api)
    assert api.raw.post("/api/estimate", json={"kind": "episode_script", "model": "-", "film_id": f}).status_code == 422
    api.put(f"/api/films/{f}", json={"synopsis": "Rani pulang ke desa."})
    cast(api, f, [char(api, name="Rani")[0]], [loc(api)])
    est = estimate(api, kind="episode_script", model="-", film_id=f)
    assert 0 < est["high"] < 0.01
    good = FORMATTED_SCRIPT
    fake.chat_content = json.dumps({"script": good})
    before = api.studio.db.committed_today()
    r = api.raw.post(f"/api/films/{f}/script/draft", json={"confirmed_cost": est["high"]})
    assert r.status_code == 200, r.text
    assert r.json()["script"] == good.strip() and r.json()["scenes"] == 1
    assert jr(api, f)["script"] == ""                                                     # draf belum disimpan
    assert api.studio.db.committed_today() == pytest.approx(before + 0.002)
    assert api.raw.post(f"/api/films/{f}/script/draft", json={}).status_code == 409        # wajib konfirmasi biaya
    fake.chat_content = json.dumps({"script": "   "})
    assert api.raw.post(f"/api/films/{f}/script/draft", json={"confirmed_cost": est["high"]}).status_code == 502


# ---------- AI: pecah naskah ----------
def split_setup(api):
    f = film(api)
    a, b = char(api, name="Rani")[0], char(api, name="Budi")[0]
    l1 = loc(api)
    cast(api, f, [a, b], [l1])
    api.put(f"/api/films/{f}", json={"script": "@[Rani] masuk ke #[Warung]. @[Budi] menyusul dan menyapa."})
    return f, a, b, l1


def split(api, f, **kw):
    est = estimate(api, kind="episode_split", model="-", film_id=f)
    return api.raw.post(f"/api/films/{f}/split", json={"confirmed_cost": est["high"], **kw})


def test_split_draft_cleans_foreign_ids_and_does_not_save(api, fake):
    f, a, b, l1 = split_setup(api)
    fake.chat_content = json.dumps({"scenes": [
        {"location_id": l1, "time_of_day": "senja", "camera": "wide", "planned_seconds": 6, "excerpt": "Rani masuk",
         "cast": [{"character_id": a, "action": "masuk"}, {"character_id": "hantu", "action": "x"}]},
        {"location_id": "asing", "cast": [{"character_id": b, "action": "menyapa"}]}]})
    r = split(api, f)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["scenes"]) == 2 and body["scenes"][1]["location_id"] is None
    assert [c["character_id"] for c in body["scenes"][0]["cast"]] == [a] and len(body["warnings"]) == 2
    assert api.get(f"/api/films/{f}").json()["scene_count"] == 0                              # draf, belum jadi adegan
    sent = json.loads(chat_calls(fake)[-1].content)["messages"][1]["content"]
    assert f"id={a}" in sent and "@[Rani] masuk ke #[Warung]" in sent


def test_split_requires_script_and_reports_unusable_answers(api, fake):
    f = film(api)
    assert api.raw.post("/api/estimate", json={"kind": "episode_split", "model": "-", "film_id": f}).status_code == 422
    f, *_ = split_setup(api)
    fake.chat_content = json.dumps({"scenes": []})
    assert split(api, f).status_code == 502
    fake.chat_content = "bukan json"
    before = api.studio.db.committed_today()
    assert split(api, f).status_code == 502
    assert api.studio.db.committed_today() > before                                         # biaya tetap tercatat


def draft_scenes(a, b, l1, n=2):
    return [{"location_id": l1, "time_of_day": "senja", "camera": "wide", "planned_seconds": 6, "excerpt": f"potongan {i}",
             "dialogue": "Rani: halo", "extra_prompt": "hangat", "cast": [{"character_id": a, "action": "masuk"},
                                                                          {"character_id": b, "action": "menyapa"}]} for i in range(n)]


def test_apply_split_append_sets_hash_excerpt_and_flags_script_change(api):
    f, a, b, l1 = split_setup(api)
    first = scene(api, f)
    r = api.post(f"/api/films/{f}/split/apply", json={"scenes": draft_scenes(a, b, l1), "mode": "append"})
    assert r.status_code == 200, r.text
    scenes = r.json()["scenes"]
    assert len(scenes) == 3 and scenes[0]["id"] == first["id"]                               # ditambah di akhir
    assert scenes[1]["script_excerpt"] == "potongan 0" and scenes[1]["planned_seconds"] == 6
    assert [c["character_id"] for c in scenes[1]["cast"]] == [a, b] and scenes[1]["location"]["id"] == l1
    assert jr(api, f)["script_changed"] is False
    api.put(f"/api/films/{f}", json={"script": "naskah baru"})
    assert jr(api, f)["script_changed"] is True


def test_apply_split_revalidates_against_current_episode_cast(api):
    f, a, b, l1 = split_setup(api)
    cast(api, f, [a], [l1])                                                                   # Budi dikeluarkan setelah draf dibuat
    r = api.post(f"/api/films/{f}/split/apply", json={"scenes": draft_scenes(a, b, l1, 1), "mode": "append"})
    assert r.status_code == 200 and [c["character_id"] for c in r.json()["scenes"][0]["cast"]] == [a]
    assert r.json()["warnings"]


def test_apply_split_replace_is_blocked_by_results_and_works_otherwise(api):
    f, a, b, l1 = split_setup(api)
    s1, s2 = scene(api, f)["id"], scene(api, f)["id"]
    put(api, s2, keyframe_image_id=up(api))
    r = api.post(f"/api/films/{f}/split/apply", json={"scenes": draft_scenes(a, b, l1, 1), "mode": "replace"})
    assert r.status_code == 409 and "2" in r.json()["detail"]
    assert api.get(f"/api/films/{f}").json()["scene_count"] == 2                              # tidak ada yang berubah
    put(api, s2, keyframe_image_id=None)
    r = api.post(f"/api/films/{f}/split/apply", json={"scenes": draft_scenes(a, b, l1, 3), "mode": "replace"})
    assert r.status_code == 200 and len(r.json()["scenes"]) == 3
    assert s1 not in [x["id"] for x in r.json()["scenes"]]


def test_apply_split_limits_and_mode(api):
    f, a, b, l1 = split_setup(api)
    assert api.post(f"/api/films/{f}/split/apply", json={"scenes": draft_scenes(a, b, l1, 1), "mode": "tukar"}).status_code == 422
    assert api.post(f"/api/films/{f}/split/apply", json={"scenes": [], "mode": "append"}).status_code == 422
    for _ in range(5):
        assert api.post(f"/api/films/{f}/split/apply", json={"scenes": draft_scenes(a, b, l1, 10), "mode": "append"}).status_code == 200
    r = api.post(f"/api/films/{f}/split/apply", json={"scenes": draft_scenes(a, b, l1, 1), "mode": "append"})
    assert r.status_code == 422 and "50" in r.json()["detail"]


def test_structure_changes_are_refused_while_rendering(api):
    f, a, b, l1 = split_setup(api)
    api.studio.db.execute("UPDATE films SET render_status = 'rendering' WHERE id = ?", (f,))
    assert cast(api, f, [a]).status_code == 409
    assert api.post(f"/api/films/{f}/split/apply", json={"scenes": draft_scenes(a, b, l1, 1), "mode": "append"}).status_code == 409


# ---------- kemajuan ----------
def test_progress_counts_scene_results(api):
    _, s, _ = ready_scene(api)
    f = first_film(api)
    scene(api, f, location_id=None)
    api.put(f"/api/films/{f}", json={"previs_skipped": True})
    p = jr(api, f)
    assert p["progress"]["scenes"] == 2 and p["progress"]["keyframe"] == 0 and p["previs_skipped"] is True
    put(api, s, keyframe_image_id=up(api))
    assert jr(api, f)["progress"]["keyframe"] == 1


# ---------- video dari previs ----------
class FakePublic:
    def publish(self, path, content_type="video/mp4"):
        return "k", "https://pub.test/previs.mp4"

    def delete(self, key):
        pass

    def cleanup(self, older):
        return 0


SEEDANCE = "bytedance/seedance-2.5"


def previs_ready(api, tmp_path):
    _, s, ids = ready_scene(api, ("Rani", "Budi"))
    api.studio.public = FakePublic()
    vid = make_video(tmp_path / "previs.mp4", seconds=1).read_bytes()
    r = api.post(f"/api/scenes/{s}/previs", files={"file": ("p.mp4", vid, "video/mp4")})
    assert r.status_code == 200, r.text
    return s, ids


def test_previs_video_needs_previs_first(api):
    _, s, _ = ready_scene(api)
    r = api.raw.post("/api/estimate", json={"kind": "scene_previs_video", "model": SEEDANCE, "scene_id": s, "duration": 4})
    assert r.status_code == 422 and "previs" in r.json()["detail"]


def test_previs_video_sends_previs_plus_character_and_location_images(api, fake, tmp_path):
    s, ids = previs_ready(api, tmp_path)
    est = estimate(api, kind="scene_previs_video", model=SEEDANCE, scene_id=s, duration=4, resolution="720p")
    body = {"model": SEEDANCE, "duration": 4, "resolution": "720p", "confirmed_cost": est["high"],
            "accept_unknown_cost": est["confidence"] == "unknown"}
    r = api.raw.post(f"/api/scenes/{s}/previs-video", json=body)
    assert r.status_code == 200, r.text
    sent = fake.last_json("/videos")
    refs = sent["input_references"]
    assert refs[0] == {"type": "video_url", "video_url": {"url": "https://pub.test/previs.mp4"}}
    assert [x["type"] for x in refs] == ["video_url", "image_url", "image_url", "image_url"]    # 2 pemeran + latar
    assert "Video 1 is a rough 3D previs" in sent["prompt"] and "CHARACTER Rani" in sent["prompt"] and "the LOCATION Sawah" in sent["prompt"]
    clip = api.studio.db.one("SELECT * FROM clips WHERE kind = 'motion'")
    assert clip["scene_id"] == s
    assert r.json()["clip_id"] == clip["id"] and r.json()["status"] == "video_diproses"
    assert api.studio.db.committed_today() > 0


def test_previs_video_of_other_workspace_is_404(api, tmp_path):
    s, _ = previs_ready(api, tmp_path)
    r = api.raw.post(f"/api/scenes/{s}/previs-video", json={"model": SEEDANCE, "confirmed_cost": 1, "accept_unknown_cost": True},
                     **hdr(mkws(api, "lain")))
    assert r.status_code == 404
