"""Plan 18 Revisi 5: naskah berformat shot Seedance 2.0 (pengurai, validasi keluaran AI, adegan+beat gratis)."""
import json

import pytest

from app import script_format as sf
from test_journey import FORMATTED_SCRIPT, cast, chat_calls, jr, loc
from test_scene_generate import estimate
from test_scenes import film
from test_workspaces import char

CHARS = [{"id": "c1", "name": "Rani"}, {"id": "c2", "name": "Budi"}]
LOCS = [{"id": "l1", "name": "Warung"}]


def block(n=1, shots=((0, 2), (2, 4)), fmt="4s / 2 SHOTS / drama", subject="@[Rani], gadis desa", extra=""):
    t = lambda x: f"{x // 60}:{x % 60:02d}"
    lines = [f"ADEGAN {n} — #[Warung]", f"FORMAT: {fmt}", f"SUBJECT: {subject}", "WARDROBE: Rani: kebaya", "ENVIRONMENT: #[Warung], sore", "MOOD: tenang"]
    lines += [f"SHOT {i} — {t(a)} to {t(b)}, MS, 35mm, locked. @[Rani] melangkah.{extra}" for i, (a, b) in enumerate(shots, 1)]
    return "\n".join(lines)


def test_is_formatted_needs_format_label_and_shot_line():
    assert sf.is_formatted(FORMATTED_SCRIPT)
    assert not sf.is_formatted("@[Rani] tiba di #[Warung].")
    assert not sf.is_formatted("FORMAT: 4s / 1 SHOT\nbukan shot")


def test_parse_maps_blocks_to_scenes_and_beats():
    r = sf.parse(FORMATTED_SCRIPT, CHARS, LOCS)
    assert r["errors"] == [] and len(r["scenes"]) == 1
    s = r["scenes"][0]
    assert (s["location_id"], s["planned_seconds"], s["extra_prompt"]) == ("l1", 4, "tenang")
    assert [c["character_id"] for c in s["cast"]] == ["c1"] and s["dialogue"] == "Rani: Aku pulang"
    b = s["beats"]
    assert [(x["start"], x["end"], x["size"], x["lens"], x["camera"]) for x in b] == [(0, 2, "WS", "24", "locked"), (2, 4, "MCU", "85", "slow push-in")]
    assert b[0]["action"] == "Rani tiba di warung" and b[1]["dialogue"] == [{"character_id": "c1", "text": "Aku pulang"}]
    assert "@[" not in b[0]["action"]


def test_parse_two_blocks_each_checked_independently():
    text = block(1) + "\n\n" + block(2, shots=((0, 3), (3, 6)), fmt="6s / 2 SHOTS / drama") + "\n\n" + block(3, shots=((0, 20),), fmt="20s / 1 SHOTS")
    r = sf.parse(text, CHARS, LOCS)
    assert len(r["scenes"]) == 2 and len(r["errors"]) == 1 and "adegan 3" in r["errors"][0] and "15 dtk" in r["errors"][0]


@pytest.mark.parametrize("text,msg", [
    (block().replace("MOOD: tenang\n", "").replace("SUBJECT: @[Rani], gadis desa\n", ""), "SUBJECT"),
    (block(shots=((0, 2), (3, 5))), "harus mulai di 2"),
    (block(subject="@[Rani] @[Budi] @[Siti] @[Tono]", extra=" @[Budi] @[Rani]"), "adegan 1"),
    ("FORMAT: 4s / 0 SHOTS\nSUBJECT: x\nENVIRONMENT: y", "tidak ada"),
])
def test_parse_reports_errors_with_scene_number(text, msg):
    chars = CHARS + [{"id": "c3", "name": "Siti"}, {"id": "c4", "name": "Tono"}]
    r = sf.parse(text, chars, LOCS)
    assert r["errors"] and msg in " ".join(r["errors"]), r


def test_unknown_names_are_warnings_not_new_entities():
    r = sf.parse(block(extra=" @[Hantu] mengintip."), CHARS, LOCS)
    assert r["errors"] == [] and any("Hantu" in w for w in r["warnings"])
    assert [c["character_id"] for c in r["scenes"][0]["cast"]] == ["c1"]


def test_format_shot_count_mismatch_and_long_shot_are_warnings():
    r = sf.parse(block(fmt="4s / 5 SHOTS / x", shots=((0, 4),)), CHARS, LOCS)
    assert r["errors"] == [] and any("5 shot" in w for w in r["warnings"]) and any("1-3 dtk" in w for w in r["warnings"])


# ---------- terhubung ke alur episode ----------
def setup(api):
    f = film(api)
    cast(api, f, [char(api, name="Rani")[0]], [loc(api, name="Warung")])
    api.put(f"/api/films/{f}", json={"synopsis": "Rani pulang."})
    return f


def draft(api, f):
    est = estimate(api, kind="episode_script", model="-", film_id=f)
    return api.raw.post(f"/api/films/{f}/script/draft", json={"confirmed_cost": est["high"]})


def test_ai_script_that_breaks_format_is_retried_once_with_errors_then_accepted(api, fake):
    f = setup(api)
    fake.chat_sequence = [json.dumps({"script": "Rani tiba di warung."}), json.dumps({"script": FORMATTED_SCRIPT})]
    r = draft(api, f)
    assert r.status_code == 200, r.text
    assert r.json()["attempts"] == 2 and len(chat_calls(fake)) == 2
    assert "previous script was rejected" in json.loads(chat_calls(fake)[1].content)["messages"][1]["content"]


def test_ai_script_always_wrong_is_502_and_both_calls_cost(api, fake):
    f = setup(api)
    fake.chat_content = json.dumps({"script": "Rani tiba di warung."})
    before = api.studio.db.committed_today()
    assert draft(api, f).status_code == 502
    assert len(chat_calls(fake)) == 2 and api.studio.db.committed_today() > before


def test_system_prompt_states_the_format_rules(api, fake):
    f = setup(api)
    fake.chat_content = json.dumps({"script": FORMATTED_SCRIPT})
    draft(api, f)
    system = json.loads(chat_calls(fake)[0].content)["messages"][0]["content"]
    for needle in ["FORMAT:", "SUBJECT:", "WARDROBE:", "ENVIRONMENT:", "MOOD:", "SHOT 1 — 0:00 to 0:02", "1 to 3 seconds", "at most 15 seconds", 'says: "']:
        assert needle in system


def test_free_split_from_formatted_script_then_apply_creates_scenes_and_beats(api, fake):
    f = setup(api)
    api.put(f"/api/films/{f}", json={"script": FORMATTED_SCRIPT})
    info = jr(api, f)["format"]
    assert info["detected"] and (info["scenes"], info["shots"], info["errors"]) == (1, 2, [])
    r = api.raw.post(f"/api/films/{f}/split/format")
    assert r.status_code == 200 and r.json()["cost"] == 0 and not chat_calls(fake)      # tanpa AI, tanpa biaya
    draft_scenes = r.json()["scenes"]
    ap = api.raw.post(f"/api/films/{f}/split/apply", json={"scenes": draft_scenes, "mode": "append"})
    assert ap.status_code == 200, ap.text
    sid = ap.json()["scenes"][0]["id"]
    beats = api.get(f"/api/scenes/{sid}/beats").json()["beats"]
    assert [(b["start"], b["end"], b["size"], b["lens"]) for b in beats] == [(0, 2, "WS", "24"), (2, 4, "MCU", "85")]
    assert api.get(f"/api/films/{f}").json()["scenes"][0]["planned_seconds"] == 4


def test_split_format_refuses_prose_and_broken_blocks(api):
    f = setup(api)
    api.put(f"/api/films/{f}", json={"script": "@[Rani] tiba di #[Warung]."})
    assert api.raw.post(f"/api/films/{f}/split/format").status_code == 422
    api.put(f"/api/films/{f}", json={"script": block(shots=((0, 20),), fmt="20s / 1 SHOTS")})
    r = api.raw.post(f"/api/films/{f}/split/format")
    assert r.status_code == 422 and "15 dtk" in r.json()["detail"]


def test_apply_with_one_bad_beat_creates_no_scene_at_all(api):
    f = setup(api)
    api.put(f"/api/films/{f}", json={"script": FORMATTED_SCRIPT})
    d = api.raw.post(f"/api/films/{f}/split/format").json()["scenes"]
    d[0]["beats"][1]["start"] = 9      # celah → tidak valid
    assert api.raw.post(f"/api/films/{f}/split/apply", json={"scenes": d, "mode": "append"}).status_code == 422
    assert api.get(f"/api/films/{f}").json()["scene_count"] == 0


# ---------- ubah naskah dengan AI (Revisi 7) ----------
SECOND = FORMATTED_SCRIPT.replace("ADEGAN 1", "ADEGAN 2").replace("tiba di warung", "duduk di warung")
TWO = FORMATTED_SCRIPT.strip() + "\n\n" + SECOND.strip()


def revise(api, f, instruction="ubah adegan 2 jadi malam", **kw):
    est = estimate(api, kind="script_revise", model="-", film_id=f)
    return api.raw.post(f"/api/films/{f}/script/revise", json={"instruction": instruction, "confirmed_cost": est["high"], **kw})


def with_script(api, text=TWO):
    f = setup(api)
    api.put(f"/api/films/{f}", json={"script": text})
    return f


def test_compare_matches_by_content_not_number():
    new = FORMATTED_SCRIPT.replace("ADEGAN 1", "ADEGAN 2").strip() + "\n\n" + block(1, fmt="4s / 2 SHOTS / baru")   # disisip di depan, nomor bergeser
    c = sf.compare(TWO, new)
    assert [(s["n"], s["changed"]) for s in c["scenes"]] == [(1, False), (2, True)] and c["previous_scenes"] == 2 and c["removed"] == 1
    assert c["scenes"][1]["previous"] is not None and "ADEGAN 2" in c["scenes"][1]["previous"]
    same = sf.compare(TWO, TWO)
    assert [s["changed"] for s in same["scenes"]] == [False, False] and same["removed"] == 0


def test_revise_needs_script_instruction_and_confirmation(api, fake):
    f = setup(api)
    assert api.raw.post("/api/estimate", json={"kind": "script_revise", "model": "-", "film_id": f}).status_code == 422    # naskah kosong
    f = with_script(api)
    assert api.raw.post(f"/api/films/{f}/script/revise", json={"instruction": "x"}).status_code == 409 and not chat_calls(fake)
    assert revise(api, f, "  ").status_code == 422
    assert api.raw.post(f"/api/films/{f}/script/revise", json={"instruction": "x" * 501, "confirmed_cost": 1}).status_code == 422


def test_revise_returns_unsaved_draft_with_per_scene_changes(api, fake):
    f = with_script(api)
    new = TWO.replace("MOOD: tenang", "MOOD: gelap", 1)           # hanya adegan 1 yang berubah
    new = new.replace("SHOT 1 — 0:00 to 0:02, WS, 24mm, locked. @[Rani] tiba", "SHOT 1 — 0:00 to 0:02, WS, 24mm, locked. @[Rani] malam-malam tiba", 1)
    fake.chat_content = json.dumps({"script": new})
    r = revise(api, f)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["script"] == new.strip() and [s["changed"] for s in d["scenes"]] == [True, False] and d["format_before"] and d["attempts"] == 1
    assert d["scenes"][0]["previous"] and "tenang" in d["scenes"][0]["previous"]
    assert jr(api, f)["script"] == TWO                                          # draf belum disimpan
    system, user = [m["content"] for m in json.loads(chat_calls(fake)[0].content)["messages"][:2]]
    assert "copied back EXACTLY" in system and "USER INSTRUCTION" in user and "ubah adegan 2 jadi malam" in user and "CURRENT SCRIPT" in user
    assert "ADEGAN 2" in user                                                    # naskah dikirim utuh


def test_revise_converts_prose_and_breaks_format_retry_then_502(api, fake):
    f = with_script(api, "@[Rani] tiba di #[Warung]. Rani berkata halo.")
    fake.chat_sequence = [json.dumps({"script": "masih prosa"}), json.dumps({"script": FORMATTED_SCRIPT})]
    r = revise(api, f, "ubah ke format")
    assert r.status_code == 200 and r.json()["attempts"] == 2 and not r.json()["format_before"]
    assert "previous script was rejected" in json.loads(chat_calls(fake)[1].content)["messages"][1]["content"]
    fake.chat_content = json.dumps({"script": "masih prosa"})
    before = api.studio.db.committed_today()
    assert revise(api, f).status_code == 502 and api.studio.db.committed_today() > before


def test_revise_estimate_is_independent_of_instruction_length_and_output_budget_grows(api, fake):
    from app import script
    f = with_script(api)
    est = estimate(api, kind="script_revise", model="-", film_id=f)
    fake.chat_content = json.dumps({"script": TWO})
    for text in ("a", "b" * 450):
        assert api.raw.post(f"/api/films/{f}/script/revise", json={"instruction": text, "confirmed_cost": est["high"]}).status_code == 200
    assert script.revise_tokens("x" * 100) == 4000 and script.revise_tokens("x" * 100_000) == 16000
    assert 4000 < script.revise_tokens("x" * 12_000) < 16000
