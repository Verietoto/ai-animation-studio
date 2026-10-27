"""Plan 18 Revisi 8: prompt adegan sebagai sumber tunggal (latar, pemeran, beat, mood, durasi diturunkan darinya)."""
import json

from app import scene_prompt, seedance_request
from test_scenes import put
from test_storyboard_video import estimate, last_video_request, sb  # noqa: F401  (fixture sb)
from test_workspaces import char, hdr, mkws


def prompt(api, sid):
    return api.get(f"/api/scenes/{sid}/prompt").json()


def scene_json(api, sid):
    f = api.get("/api/films").json()[0]["id"]
    return next(s for s in api.get(f"/api/films/{f}").json()["scenes"] if s["id"] == sid)


def save(api, sid, text):
    return api.raw.put(f"/api/scenes/{sid}/prompt", json={"prompt": text})


def test_unsaved_scene_prompt_is_rendered_from_data_in_seedance_format(sb):
    api, sid, cid = sb
    p = prompt(api, sid)
    assert p["derived"] and p["errors"] == []
    t = p["prompt"]
    assert t.startswith("ADEGAN 1 — #[Ruang]\nFORMAT: 9s / 2 SHOTS") and "SUBJECT: @[Momon], bob hitam." in t and "ENVIRONMENT: #[Ruang]" in t
    assert "SHOT 1 — 0:00 to 0:04, wide. @[Momon] masuk." in t and 'SHOT 2 — 0:04 to 0:09. @[Momon] bicara. @[Momon] says: "Aku lapar".' in t
    assert [c["name"] for c in p["assets"]["characters"]] == ["Momon"] and p["assets"]["location"]["name"] == "Ruang"


def test_save_roundtrip_is_stable_and_does_not_pile_up_versions(sb):
    api, sid, cid = sb
    before = scene_json(api, sid)
    first = prompt(api, sid)["prompt"]
    assert save(api, sid, first).status_code == 200
    kept = prompt(api, sid)
    assert not kept["derived"] and kept["prompt"] == first
    s = scene_json(api, sid)
    assert (s["planned_seconds"], s["location"]["id"], [c["character_id"] for c in s["cast"]]) == (9, before["location"]["id"], [cid])
    beats = api.get(f"/api/scenes/{sid}/beats").json()["beats"]
    assert [(b["start"], b["end"], b["action"]) for b in beats] == [(0, 4, "Momon masuk"), (4, 9, "Momon bicara")]
    versions = len(api.get(f"/api/scenes/{sid}/beats/versions").json())
    assert save(api, sid, first).status_code == 200
    assert len(api.get(f"/api/scenes/{sid}/beats/versions").json()) == versions        # beat sama: tanpa versi baru


def test_editing_prompt_derives_location_cast_beats_mood_and_duration(sb):
    api, sid, cid = sb
    sari, _ = char(api, name="Sari")
    api.post("/api/locations", json={"name": "Dapur", "description": "uap"})
    text = ("ADEGAN 1 — #[Dapur]\nFORMAT: 6s / 2 SHOTS / komedi\nSUBJECT: @[Momon], kucing. @[Sari], gadis\nENVIRONMENT: #[Dapur], pagi\nMOOD: hangat\n"
            "SHOT 1 — 0:00 to 0:03, WS, 24mm, locked. @[Sari] menyapa.\n"
            'SHOT 2 — 0:03 to 0:06, CU, 85mm, pan. @[Momon] says: "Lapar"')
    r = save(api, sid, text)
    assert r.status_code == 200, r.text
    s = scene_json(api, sid)
    assert s["location"]["name"] == "Dapur" and s["planned_seconds"] == 6 and s["extra_prompt"] == "hangat"
    assert {c["character_id"] for c in s["cast"]} == {cid, sari} and next(c for c in s["cast"] if c["character_id"] == cid)["action"] == "melompat"   # aksi lama dipertahankan
    b = api.get(f"/api/scenes/{sid}/beats").json()["beats"]
    assert [(x["size"], x["lens"], x["camera"]) for x in b] == [("WS", "24", "locked"), ("CU", "85", "pan")]
    assert b[1]["dialogue"][0]["text"] == "Lapar" and prompt(api, sid)["prompt"] == text


def test_invalid_prompt_changes_nothing(sb):
    api, sid, cid = sb
    good = prompt(api, sid)["prompt"]
    before = (scene_json(api, sid), api.get(f"/api/scenes/{sid}/beats").json())
    for bad, msg in ((good.replace("@[Momon], bob hitam", "@[Hantu], x", 1), "Hantu"), (good.replace("#[Ruang]", "#[Nowhere]"), "Nowhere"),
                     (good + "\n\n" + good, "tepat satu blok"), (good.replace("0:04 to 0:09", "0:05 to 0:09"), "harus mulai di"), ("", "kosong")):
        r = save(api, sid, bad)
        assert r.status_code == 422 and msg in r.json()["detail"], (msg, r.text)
    assert (scene_json(api, sid), api.get(f"/api/scenes/{sid}/beats").json()) == before


def test_duplicate_names_are_an_explicit_error(sb):
    api, sid, cid = sb
    char(api, name="Momon")
    r = save(api, sid, prompt(api, sid)["prompt"])
    assert r.status_code == 422 and "bernama ganda" in r.json()["detail"]


def test_check_reports_without_saving_and_flags_assets_without_image(sb):
    api, sid, cid = sb
    good = prompt(api, sid)["prompt"]
    c = api.raw.post(f"/api/scenes/{sid}/prompt/check", json={"prompt": good.replace("#[Ruang]", "#[Nowhere]")}).json()
    assert c["errors"] and "Nowhere" in c["errors"][0]
    ok = api.raw.post(f"/api/scenes/{sid}/prompt/check", json={"prompt": good}).json()
    assert ok["errors"] == [] and [x["name"] for x in ok["will_link"]["characters"]] == ["Momon"] and prompt(api, sid)["derived"]


def test_every_other_path_clears_the_stored_prompt_so_it_is_never_stale(sb):
    api, sid, cid = sb
    base = prompt(api, sid)["prompt"]

    def stored():
        save(api, sid, base)
        assert not prompt(api, sid)["derived"]

    stored()
    api.put(f"/api/scenes/{sid}/beats", json={"beats": [{"start": 0, "end": 3, "action": "baru", "cast": [cid]}]})
    p = prompt(api, sid)
    assert p["derived"] and "SHOT 1 — 0:00 to 0:03. @[Momon] baru." in p["prompt"]
    stored()
    put(api, sid, cast=[])
    assert prompt(api, sid)["derived"] and "SUBJECT: (tanpa pemeran)" in prompt(api, sid)["prompt"]
    put(api, sid, cast=[{"character_id": cid, "outfit_id": None, "action": ""}])
    stored()
    api.raw.delete(f"/api/characters/{cid}")
    assert prompt(api, sid)["derived"] and "@[Momon]" not in prompt(api, sid)["prompt"] and "SUBJECT: (tanpa pemeran)" in prompt(api, sid)["prompt"]


def test_renaming_a_location_rewrites_the_stored_prompt(sb):
    api, sid, cid = sb
    save(api, sid, prompt(api, sid)["prompt"])
    loc = scene_json(api, sid)["location"]["id"]
    assert api.raw.put(f"/api/locations/{loc}", json={"name": "Aula"}).status_code == 200
    p = prompt(api, sid)
    assert not p["derived"] and "#[Aula]" in p["prompt"] and "#[Ruang]" not in p["prompt"] and p["errors"] == []


def test_video_prompt_comes_from_scene_prompt_and_numbers_follow_actual_references(sb, fake):
    api, sid, cid = sb
    save(api, sid, prompt(api, sid)["prompt"])
    est = estimate(api, sid)
    assert api.raw.post(f"/api/scenes/{sid}/storyboard-video", json={"confirmed_cost": est["high"]}).status_code == 200
    req = last_video_request(fake)
    assert "SUBJECT: @image_1 — Momon" in req["prompt"] and "ENVIRONMENT: Ruang (see @image_2)" in req["prompt"] and "#[" not in req["prompt"] and "@[" not in req["prompt"]
    assert req["prompt"].index("Visual style: kartun 2D.") < req["prompt"].index("SHOT 1")
    # pemeran dihapus dari prompt → tidak ada nomor basi; latar menjadi @image_1
    text = prompt(api, sid)["prompt"].replace("@[Momon], bob hitam.", "").replace("@[Momon]", "seseorang")
    assert save(api, sid, text).status_code in (200, 422)
    if save(api, sid, text).status_code == 200:
        est = estimate(api, sid)
        api.raw.post(f"/api/scenes/{sid}/storyboard-video", json={"confirmed_cost": est["high"]})
        req = last_video_request(fake)
        assert "Momon" not in req["prompt"] and len(req["input_references"]) == 1 and "(see @image_1)" in req["prompt"]


def test_preview_returns_source_and_resolved_prompt(sb):
    api, sid, cid = sb
    pv = api.get(f"/api/scenes/{sid}/storyboard-video/preview").json()
    assert "@[Momon]" in pv["scene_prompt"] and "@[" not in pv["prompt"] and "@image_1 — Momon" in pv["prompt"]


def test_scene_prompt_is_scoped_to_workspace(sb):
    api, sid, cid = sb
    other = hdr(mkws(api, "lain"))
    assert api.raw.get(f"/api/scenes/{sid}/prompt", **other).status_code == 404
    assert api.raw.put(f"/api/scenes/{sid}/prompt", json={"prompt": "x"}, **other).status_code == 404


def test_resolve_only_first_subject_mention_gets_the_image_and_unknown_locations_stay_plain():
    text = "ADEGAN 1 — #[Dapur]\nSUBJECT: @[Momon], a. @[Momon], b\nENVIRONMENT: #[Dapur] pagi\nSHOT 1 — 0:00 to 0:02. @[Momon] says: \"hi\""
    out = seedance_request.resolve(text, characters={"Momon": 3}, location=0, known_locations=set())
    assert out == "ADEGAN 1 — Dapur\nSUBJECT: @image_3 — Momon, a. Momon, b\nENVIRONMENT: Dapur pagi\nSHOT 1 — 0:00 to 0:02. Momon says: \"hi\""


def test_render_parse_render_is_stable_for_beat_cast_without_mention():
    cast = [{"character_id": "c1", "name": "Rani", "description": "gadis", "action": "", "wardrobe": ""}]
    beats = [{"start": 0.0, "end": 2.0, "size": None, "lens": None, "camera": "", "action": "menari", "cast": ["c1"], "dialogue": []}]
    a = scene_prompt.render(number=1, planned=2, genre="", location=None, time_of_day="", cast=cast, beats=beats, mood="")
    assert "@[Rani] menari" in a


# ---------- ubah prompt adegan dengan AI (Revisi 10) ----------
def revise_prompt(api, sid, instruction="pindahkan ke malam hari", **kw):
    est = estimate_prompt(api, sid)
    return api.raw.post(f"/api/scenes/{sid}/prompt/revise", json={"instruction": instruction, "confirmed_cost": est["high"], **kw})


def estimate_prompt(api, sid):
    r = api.raw.post("/api/estimate", json={"kind": "scene_prompt_revise", "model": "-", "scene_id": sid})
    assert r.status_code == 200, r.text
    return r.json()


def calls(fake):
    return [r for r in fake.requests if r.url.path.endswith("/chat/completions")]


def test_prompt_revise_needs_confirmation_and_instruction(sb, fake):
    api, sid, cid = sb
    assert api.raw.post(f"/api/scenes/{sid}/prompt/revise", json={"instruction": "x"}).status_code == 409 and not calls(fake)
    assert revise_prompt(api, sid, "  ").status_code == 422
    assert api.raw.post(f"/api/scenes/{sid}/prompt/revise", json={"instruction": "x" * 501, "confirmed_cost": 1}).status_code == 422


def test_prompt_revise_returns_validated_unsaved_draft_with_changed_lines(sb, fake):
    api, sid, cid = sb
    old = prompt(api, sid)["prompt"]
    new = old.replace("ENVIRONMENT: #[Ruang]. hangat.", "ENVIRONMENT: #[Ruang], malam. hangat.").replace("MOOD", "MOOD")
    new = new.replace("FORMAT: 9s / 2 SHOTS", "FORMAT: 9s / 2 SHOTS / thriller")
    fake.chat_content = json.dumps({"script": new})
    r = revise_prompt(api, sid)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["prompt"] == new.strip() and d["previous"] == old and d["attempts"] == 1
    lines = new.strip().splitlines()
    assert [lines[n - 1] for n in d["changed"]] == [l for l in lines if l not in old.splitlines()] and len(d["changed"]) == 2
    assert prompt(api, sid)["derived"] and prompt(api, sid)["prompt"] == old               # draf tidak tersimpan
    system, user = [m["content"] for m in json.loads(calls(fake)[0].content)["messages"][:2]]
    assert "exactly ONE scene block" in system and "USER INSTRUCTION" in user and "pindahkan ke malam hari" in user and old.splitlines()[0] in user


def test_prompt_revise_retries_once_on_invalid_output_then_502(sb, fake):
    api, sid, cid = sb
    good = prompt(api, sid)["prompt"]
    fake.chat_sequence = [json.dumps({"script": good.replace("@[Momon] bicara", "@[Hantu] bicara", 1)}), json.dumps({"script": good})]
    r = revise_prompt(api, sid)
    assert r.status_code == 200 and r.json()["attempts"] == 2
    assert "previous answer was rejected" in json.loads(calls(fake)[1].content)["messages"][1]["content"] and "Hantu" in json.loads(calls(fake)[1].content)["messages"][1]["content"]
    fake.chat_sequence = []
    n = len(calls(fake))
    fake.chat_content = json.dumps({"script": good + "\n\n" + good})                           # dua blok → tidak sah
    before = api.studio.db.committed_today()
    assert revise_prompt(api, sid).status_code == 502 and len(calls(fake)) == n + 2 and api.studio.db.committed_today() > before


def test_prompt_revise_estimate_does_not_depend_on_instruction_length(sb, fake):
    api, sid, cid = sb
    est = estimate_prompt(api, sid)
    fake.chat_content = json.dumps({"script": prompt(api, sid)["prompt"]})
    for text in ("a", "b" * 450):
        assert api.raw.post(f"/api/scenes/{sid}/prompt/revise", json={"instruction": text, "confirmed_cost": est["high"]}).status_code == 200


def test_prompt_revise_is_scoped_to_workspace(sb):
    api, sid, cid = sb
    assert api.raw.post(f"/api/scenes/{sid}/prompt/revise", json={"instruction": "x", "confirmed_cost": 1}, **hdr(mkws(api, "lain"))).status_code == 404


def test_changed_lines_is_multiset_not_positional():
    assert scene_prompt.ScenePrompt.changed_lines("a\nb\nc", "c\nb\nx\na") == [3]
    assert scene_prompt.ScenePrompt.changed_lines("a\na", "a\na\na") == [3]
