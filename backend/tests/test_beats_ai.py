"""Plan 18 Revisi 4: shot dibuat AI mengikuti format Seedance 2.0 + ukuran/lensa/genre."""
import json

from test_blockout import chat_calls
from test_scene_generate import estimate, ready_scene
from test_scenes import put


def shots(cid, durations=(2, 3, 3), **over):
    out, t = [], 0
    for i, d in enumerate(durations):
        out.append({"start": t, "end": t + d, "size": ("WS", "MCU", "CU")[i % 3], "lens": ("24", "85", "50")[i % 3], "camera": "locked",
                    "action": f"aksi {i}", "cast": [cid], "dialogue": [{"character_id": cid, "text": "Halo"}] if i == 1 else [], **over})
        t += d
    return {"shots": out}


def run(api, s, **kw):
    est = estimate(api, kind="scene_beats", model="-", scene_id=s)
    return api.raw.post(f"/api/scenes/{s}/beats/ai", json={"confirmed_cost": est["high"], **kw})


def setup(api):
    _, s, (cid,) = ready_scene(api)
    put(api, s, planned_seconds=8)
    return s, cid


def test_requires_confirmation_and_returns_unsaved_valid_draft(api, fake):
    s, cid = setup(api)
    assert api.raw.post(f"/api/scenes/{s}/beats/ai", json={}).status_code == 409 and not chat_calls(fake)
    fake.chat_content = json.dumps(shots(cid))
    r = run(api, s)
    assert r.status_code == 200, r.text
    b = r.json()
    assert [(x["start"], x["end"], x["size"], x["lens"]) for x in b["beats"]] == [(0, 2, "WS", "24"), (2, 5, "MCU", "85"), (5, 8, "CU", "50")]
    assert b["attempts"] == 1 and api.get(f"/api/scenes/{s}/beats").json()["beats"] == []   # draf, belum disimpan
    sys_prompt = json.loads(chat_calls(fake)[0].content)["messages"][0]["content"]
    assert "1 to 3 seconds" in sys_prompt and "Vary size and lens" in sys_prompt


def test_rule_break_retries_once_with_the_error_then_succeeds(api, fake):
    s, cid = setup(api)
    fake.chat_sequence = [json.dumps(shots(cid, (5, 3))), json.dumps(shots(cid))]   # jawaban pertama: shot 5 dtk
    r = run(api, s)
    assert r.status_code == 200, r.text
    assert r.json()["attempts"] == 2 and len(chat_calls(fake)) == 2
    assert "previous answer was rejected" in json.loads(chat_calls(fake)[1].content)["messages"][1]["content"]


def test_always_invalid_is_502_and_both_calls_are_recorded(api, fake):
    s, cid = setup(api)
    fake.chat_content = json.dumps(shots(cid, (4, 4)))     # shot 4 dtk melanggar aturan
    before = api.studio.db.committed_today()
    assert run(api, s).status_code == 502
    assert len(chat_calls(fake)) == 2 and api.studio.db.committed_today() > before


def test_wrong_total_and_foreign_cast_are_rejected(api, fake):
    s, cid = setup(api)
    fake.chat_content = json.dumps(shots(cid, (2, 3, 2)))  # berakhir di 7, adegan 8
    assert run(api, s).status_code == 502
    fake.chat_content = json.dumps(shots("hantu"))
    assert run(api, s).status_code == 502


def test_scene_without_material_is_422(api, fake):
    from test_scenes import film, scene
    sid = scene(api, film(api))["id"]
    assert api.raw.post(f"/api/scenes/{sid}/beats/ai", json={"confirmed_cost": 1}).status_code == 422


def test_beat_size_lens_roundtrip_and_validation(api):
    s, cid = setup(api)
    ok = api.put(f"/api/scenes/{s}/beats", json={"beats": [{"start": 0, "end": 2, "size": "mcu", "lens": "85mm", "camera": "pan"}]})
    assert ok.status_code == 200 and (ok.json()["beats"][0]["size"], ok.json()["beats"][0]["lens"]) == ("MCU", "85")
    for bad in ({"size": "XL"}, {"lens": "300"}):
        assert api.raw.put(f"/api/scenes/{s}/beats", json={"beats": [{"start": 0, "end": 2, **bad}]}).status_code == 422


def test_genre_setting_roundtrip_and_limit(api):
    assert api.put("/api/workspaces/main/settings", json={"genre": "noir heist"}).json()["genre"] == "noir heist"
    assert api.raw.put("/api/workspaces/main/settings", json={"genre": "x" * 81}).status_code == 422


# ---------- ubah adegan dengan AI (Revisi 6) ----------
def saved_scene(api):
    s, cid = setup(api)
    r = api.put(f"/api/scenes/{s}/beats", json={"beats": [
        {"start": 0, "end": 3, "size": "WS", "lens": "24", "camera": "locked", "action": "Momon masuk", "cast": [cid]},
        {"start": 3, "end": 6, "size": "MCU", "lens": "85", "camera": "pan", "action": "Momon menatap", "cast": [cid]},
        {"start": 6, "end": 8, "size": "CU", "lens": "50", "camera": "locked", "action": "Momon tidur", "cast": [cid]}]})
    assert r.status_code == 200, r.text
    return s, cid, r.json()["beats"]


def rev(api, s, instruction="ubah jadi malam", **kw):
    est = estimate(api, kind="scene_revise", model="-", scene_id=s)
    return api.raw.post(f"/api/scenes/{s}/revise", json={"instruction": instruction, "confirmed_cost": est["high"], **kw})


def answer(cid, shots, **meta):
    return json.dumps({"total_seconds": 8, "mood": "", "time_of_day": "", **meta, "shots": [
        {"cast": [cid], "dialogue": [], "camera": "locked", "size": "MS", "lens": "35", **sh} for sh in shots]})


def test_revise_needs_beats_instruction_and_confirmation(api, fake):
    s, cid = setup(api)
    assert api.raw.post("/api/estimate", json={"kind": "scene_revise", "model": "-", "scene_id": s}).status_code == 422   # belum ada beat
    s, cid, _ = saved_scene(api)
    assert api.raw.post(f"/api/scenes/{s}/revise", json={"instruction": "x"}).status_code == 409 and not chat_calls(fake)
    assert rev(api, s, "   ").status_code == 422
    assert api.raw.post(f"/api/scenes/{s}/revise", json={"instruction": "x" * 501, "confirmed_cost": 1}).status_code == 422


def test_revise_returns_unsaved_draft_keeping_ids_and_flagging_changes(api, fake):
    s, cid, old = saved_scene(api)
    fake.chat_content = answer(cid, [
        dict(keep=1, start=0, end=3, size="WS", lens="24", camera="locked", action="Momon masuk"),          # tak berubah
        dict(keep=2, start=3, end=6, size="MCU", lens="85", camera="pan", action="Momon menatap bulan"),    # diedit
        dict(keep=None, start=6, end=8, action="Momon mengeong")], mood="sunyi", time_of_day="malam")
    r = rev(api, s, "ubah jadi malam")
    assert r.status_code == 200, r.text
    d = r.json()
    assert [b["id"] for b in d["beats"][:2]] == [old[0]["id"], old[1]["id"]] and d["beats"][2]["id"] not in {o["id"] for o in old}
    assert [(b["changed"], b["from"]) for b in d["beats"]] == [(False, 1), (True, 2), (True, None)]
    assert (d["mood"], d["time_of_day"], d["mood_changed"], d["time_changed"], d["attempts"]) == ("sunyi", "malam", True, True, 1)
    assert api.get(f"/api/scenes/{s}/beats").json()["beats"][1]["action"] == "Momon menatap"        # draf belum tersimpan
    user = json.loads(chat_calls(fake)[0].content)["messages"][1]["content"]
    assert "USER INSTRUCTION" in user and "ubah jadi malam" in user and '"action": "Momon menatap"' in user


def test_revise_can_change_total_and_ignores_bad_keep(api, fake):
    s, cid, old = saved_scene(api)
    fake.chat_content = answer(cid, [dict(keep=1, start=0, end=3, action="a"), dict(keep=1, start=3, end=6, action="b"),
                                      dict(keep=99, start=6, end=8, action="c")][:2] + [], total_seconds=6)
    d = rev(api, s, "jadikan 6 detik").json()
    assert d["total_seconds"] == 6 and d["previous_seconds"] == 8
    assert [b["from"] for b in d["beats"]] == [1, None]                    # keep ganda: yang kedua dianggap shot baru
    fake.chat_content = answer(cid, [dict(keep=99, start=0, end=3, action="a"), dict(keep=True, start=3, end=8 - 2, action="b"),
                                      dict(keep=None, start=6, end=8, action="c")])
    assert [b["from"] for b in rev(api, s).json()["beats"]] == [None, None, None]


def test_revise_rule_break_retries_once_then_502(api, fake):
    s, cid, _ = saved_scene(api)
    fake.chat_sequence = [answer(cid, [dict(keep=1, start=0, end=5, action="a"), dict(keep=2, start=5, end=8, action="b")]),   # shot 5 dtk
                          answer(cid, [dict(keep=1, start=0, end=4, action="a"), dict(keep=2, start=4, end=8, action="b")])]   # tetap salah
    assert rev(api, s).status_code == 502 and len(chat_calls(fake)) == 2
    assert "previous answer was rejected" in json.loads(chat_calls(fake)[1].content)["messages"][1]["content"]
    fake.chat_sequence = [answer(cid, [dict(keep=1, start=0, end=5, action="a")]), answer(cid, [dict(keep=1, start=0, end=3, action="a"), dict(keep=2, start=3, end=6, action="b"), dict(keep=3, start=6, end=8, action="c")])]
    r = rev(api, s)
    assert r.status_code == 200 and r.json()["attempts"] == 2


def test_revise_estimate_is_independent_of_instruction_length(api, fake):
    s, cid, _ = saved_scene(api)
    est = estimate(api, kind="scene_revise", model="-", scene_id=s)
    fake.chat_content = answer(cid, [dict(keep=1, start=0, end=3, action="a"), dict(keep=2, start=3, end=6, action="b"), dict(keep=3, start=6, end=8, action="c")])
    for text in ("a", "b" * 400):
        assert api.raw.post(f"/api/scenes/{s}/revise", json={"instruction": text, "confirmed_cost": est["high"]}).status_code == 200


def test_revise_is_scoped_to_workspace(api):
    from test_workspaces import hdr, mkws
    s, cid, _ = saved_scene(api)
    assert api.raw.post(f"/api/scenes/{s}/revise", json={"instruction": "x", "confirmed_cost": 1}, **hdr(mkws(api, "lain"))).status_code == 404
