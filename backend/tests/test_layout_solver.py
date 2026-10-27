import json
import math

import pytest

from app import blockout, layout_solver, vocab
from app.service import ServiceError
from test_scene_generate import ready_scene
from test_scenes import put
from test_workspaces import hdr, mkws


CAM = {"keys": [{"t": 0, "pos": [0, 1.5, 6], "target": [0, 1, 0], "mm": 35}]}


def p(pid, type="box", **kw):
    targets = [kw[k] for k in ("on", "near") if k in kw]            # target relasi dianggap ada (di properti lain / set)
    return blockout.clean({"duration": 5, "camera": CAM, "props": [{"id": pid, "type": type, **kw}]}, [], targets)["props"][0]


def solve(*props, actors=(), bounds=None, set_objects=()):
    return layout_solver.solve(list(set_objects), list(props), list(actors), bounds)


def by(out, pid):
    return next(o for o in out if o["id"] == pid)


def gap(a, b):
    ax, az = layout_solver.half_extent(a["dims"], a["rot"][1])
    bx, bz = layout_solver.half_extent(b["dims"], b["rot"][1])
    return min(ax + bx - abs(a["pos"][0] - b["pos"][0]), az + bz - abs(a["pos"][2] - b["pos"][2]))


# ---------- kosakata ----------
def test_vocabulary_is_consistent():
    v = vocab.load()
    for name, body in v["bodies"].items():
        assert set(body["limits"]) == set(body["joints"]), name
        for pose, d in body["poses"].items():
            assert set(d["joints"]) <= set(body["joints"]), (name, pose)
        assert {t["joint"] for t in body["gait"]["terms"]} <= set(body["joints"])
    assert all(all(x > 0 for x in pre["size"]) for pre in v["prefabs"].values())
    assert set(v["times"]) == {"pagi", "siang", "senja", "malam"}


def test_fov_matches_the_typescript_formula_values():
    assert vocab.fov_for(35, 16 / 9) == pytest.approx(37.85, abs=0.01)
    assert vocab.fov_for(35, 9 / 16) == pytest.approx(62.73, abs=0.01)
    assert vocab.fov_for(24, 16 / 9) == pytest.approx(53.13, abs=0.01)


# ---------- validasi v2 ----------
def test_v1_layout_is_upgraded_to_v2():
    v1 = {"version": 1, "duration": 4, "camera": CAM, "actors": [{"character_id": "c1", "keys": [{"t": 0, "pos": [0, 0, 0], "pose": "walk"}]}],
          "props": [{"type": "box", "pos": [2, 0.5, 0], "scale": [1, 1, 1], "rot": [0, 30, 0]}]}
    out = blockout.clean(v1, ["c1"])
    assert out["version"] == 2 and out["actors"][0]["body"] == "humanoid" and out["environment"] == {}
    pr = out["props"][0]
    assert pr["id"] == "p1" and pr["pos"] == [2, 0, 0] and pr["rot"] == [0, 30, 0]       # v1: pos tengah (y 0,5) -> v2: alas (y 0) and pr["size"] == [1, 1, 1] and pr["color"] == "#8a8a8a"


def test_v2_props_relations_ids_and_warnings():
    raw = {"duration": 5, "camera": CAM, "environment": {"time": "senja", "weather": "mars"}, "props": [
        {"id": "meja1", "type": "table", "against": "north"}, {"id": "cangkir", "type": "cup", "on": "meja1"},
        {"id": "meja1", "type": "chair", "near": "meja1"},                       # id ganda -> diganti
        {"type": "tree", "near": "tidak-ada"}, {"id": "lampu", "type": "lamp", "material": {"emissive": 1, "roughness": 0.4}, "color": "#ffcc66"}]}
    out, warn = blockout.clean_report(raw, [], ["kursi_set"])
    ids = [x["id"] for x in out["props"]]
    assert ids[0] == "meja1" and len(set(ids)) == 5 and out["props"][1]["on"] == "meja1" and out["props"][2]["near"] == "meja1"
    assert out["props"][3]["at"] == [0.0, 0.0] and any("tidak valid" in w for w in warn) and any("weather" in w for w in warn)
    assert out["environment"] == {"time": "senja"} and out["props"][4]["material"] == {"emissive": 1.0, "roughness": 0.4}
    ok = blockout.clean({"duration": 5, "camera": CAM, "props": [{"id": "x", "type": "chair", "near": "kursi_set"}]}, [], ["kursi_set"])
    assert ok["props"][0]["near"] == "kursi_set"


@pytest.mark.parametrize("mutate,msg", [
    (lambda r: r["props"][0].update(type="pesawat"), "jenis properti"),
    (lambda r: r["props"][0].update(color="biru"), "warna"),
    (lambda r: r["props"][0].update(scale=-1), "prop.scale"),
    (lambda r: r["actors"][0].update(body="naga"), "jenis tubuh"),
    (lambda r: r["actors"][0]["keys"][0].update(pose="jump"), "pose tidak dikenal"),          # jump hanya untuk berkaki empat
    (lambda r: r["actors"][0]["keys"][0].update(joints={"tail": [0, 0, 0]}), "sendi tidak dikenal"),
])
def test_v2_rejects_invalid_values(mutate, msg):
    raw = {"duration": 5, "camera": CAM, "props": [{"id": "a", "type": "box"}],
           "actors": [{"character_id": "c1", "body": "humanoid", "keys": [{"t": 0, "pos": [0, 0, 0]}]}]}
    mutate(raw)
    with pytest.raises(ServiceError) as exc:
        blockout.clean(raw, ["c1"])
    assert exc.value.status == 422 and msg in str(exc.value)


def test_quadruped_accepts_its_own_poses_and_joints():
    raw = {"duration": 5, "camera": CAM, "actors": [{"character_id": "cat", "body": "quadruped", "keys": [
        {"t": 0, "pos": [0, 0, 0], "pose": "sit", "joints": {"tail": [10, 20, 0]}}, {"t": 2, "pos": [1, 0, 0], "pose": "jump"}]}]}
    out = blockout.clean(raw, ["cat"])
    assert out["actors"][0]["body"] == "quadruped" and [k["pose"] for k in out["actors"][0]["keys"]] == ["sit", "jump"]


# ---------- pemecah ----------
def test_against_wall_sets_position_and_facing():
    out, warn = solve(p("meja", "table", against="north"), p("rak", "shelf", against="east", offset=2), p("sofa", "sofa", against="south"),
                      p("pintu", "door", against="west"))
    w, d = layout_solver.DEFAULT_BOUNDS
    meja = by(out, "meja")
    assert meja["pos"][2] == pytest.approx(-d / 2 + 0.4) and meja["rot"][1] == 0
    rak = by(out, "rak")
    assert rak["pos"][0] == pytest.approx(w / 2 - 0.175) and rak["pos"][2] == pytest.approx(2) and rak["rot"][1] == 270
    assert by(out, "sofa")["rot"][1] == 180 and by(out, "pintu")["rot"][1] == 90 and not warn


def test_on_places_item_exactly_on_the_top_surface_and_follows_parent():
    out, warn = solve(p("meja", "table", at=[2, 3]), p("cangkir", "cup", on="meja", dx=0.3, dz=-0.1), p("piring", "box", on="meja", size=[0.25, 0.03, 0.25]))
    meja, cup = by(out, "meja"), by(out, "cangkir")
    assert cup["pos"][1] == pytest.approx(meja["dims"][1]) and cup["pos"][0] == pytest.approx(2.3) and cup["pos"][2] == pytest.approx(2.9)
    assert by(out, "piring")["pos"][1] == pytest.approx(0.75) and not warn
    far, _ = solve(p("meja", "table", at=[0, 0]), p("cangkir", "cup", on="meja", dx=5))
    assert abs(by(far, "cangkir")["pos"][0]) <= 0.7 - 0.045 + 1e-6                               # tidak jatuh dari meja


def test_on_a_non_flat_parent_warns_and_sits_beside_it():
    out, warn = solve(p("pohon", "tree", at=[0, 0]), p("cangkir", "cup", on="pohon"))
    assert any("permukaan datar" in w for w in warn) and by(out, "cangkir")["pos"][1] == 0


def test_stacked_on_chain_and_cycles():
    out, _ = solve(p("meja", "table", at=[0, 0]), p("kotak", "crate", on="meja"), p("cangkir", "cup", on="kotak"))
    assert by(out, "cangkir")["pos"][1] == pytest.approx(0.75 + 0.6)
    raw = {"duration": 5, "camera": CAM, "props": [{"id": "a", "type": "crate", "on": "b"}, {"id": "b", "type": "crate", "on": "a"}]}
    out2, warn2 = solve(*blockout.clean(raw, [])["props"])
    assert len(warn2) == 2 and all(o["pos"][1] == 0 for o in out2)                                # siklus: ditaruh di lantai dengan peringatan


def test_many_objects_at_the_same_spot_are_pushed_apart_inside_bounds():
    props = [p(f"b{i}", "crate", at=[0, 0]) for i in range(12)]
    out, warn = solve(*props)
    w, d = layout_solver.DEFAULT_BOUNDS
    for i, a in enumerate(out):
        hx, hz = layout_solver.half_extent(a["dims"], a["rot"][1])
        assert abs(a["pos"][0]) + hx <= w / 2 + 1e-6 and abs(a["pos"][2]) + hz <= d / 2 + 1e-6
        for b in out[i + 1:]:
            assert gap(a, b) <= 0.02 + 1e-6, (a["id"], b["id"], gap(a, b))                         # tidak bertumpuk lebih dari 2 cm
    assert not warn


def test_fixed_objects_stay_and_others_avoid_them_and_actors():
    out, _ = solve(p("tetap", "crate", pos=[1, 0, 1]), p("geser", "crate", at=[1, 1]))
    assert by(out, "tetap")["pos"] == [1, 0, 1] and gap(by(out, "tetap"), by(out, "geser")) <= 0.02 + 1e-6
    out2, _ = solve(p("kursi", "chair", at=[0.1, 0.1]), actors=[(0, 0)])
    k = by(out2, "kursi")
    assert max(abs(k["pos"][0]), abs(k["pos"][2])) >= layout_solver.ACTOR_HALF + 0.2               # keluar dari jejak aktor


def test_wall_objects_slide_only_along_the_wall():
    out, _ = solve(p("m1", "table", against="north"), p("m2", "table", against="north"))
    a, b = by(out, "m1"), by(out, "m2")
    assert a["pos"][2] == pytest.approx(b["pos"][2]) and abs(a["pos"][0] - b["pos"][0]) >= 1.4 - 1e-6


def test_set_objects_and_scene_props_share_one_space_and_layers_are_tagged():
    setobj = [p("kursi_set", "chair", at=[0, 0])]
    out, _ = solve(p("cangkir", "cup", near="kursi_set"), set_objects=setobj)
    assert by(out, "kursi_set")["layer"] == "set" and by(out, "cangkir")["layer"] == "scene"
    c, k = by(out, "cangkir"), by(out, "kursi_set")
    assert math.dist((c["pos"][0], c["pos"][2]), (k["pos"][0], k["pos"][2])) >= 0.3


def test_solver_is_deterministic():
    props = [p("a", "table", against="north"), p("b", "chair", near="a"), p("c", "chair", near="a"), p("d", "crate", at=[0, 0]), p("e", "crate", at=[0, 0])]
    assert solve(*props) == solve(*props)


# ---------- bingkai kamera ----------
def test_frame_actors_keeps_a_good_camera_and_fixes_a_bad_one():
    keys = [{"t": 0, "pos": [0, 1.5, 6], "target": [0, 1, 0], "mm": 35}]
    same, warn = layout_solver.frame_actors(keys, [(0, 0)], 16 / 9)
    assert same == keys and warn == []
    fixed, warn = layout_solver.frame_actors(keys, [(7, 0), (-7, 0)], 16 / 9)                      # terlalu lebar untuk 35 mm dari 6 m
    assert warn and (fixed[0]["pos"][2] > 6 or fixed[0]["mm"] < 35)
    assert keys[0]["pos"] == [0, 1.5, 6]                                                           # masukan tidak diubah


def test_frame_actors_reports_when_nothing_works():
    keys = [{"t": 0, "pos": [0, 1.5, 6], "target": [0, 1, 0], "mm": 35}]
    _, warn = layout_solver.frame_actors(keys, [(40, 0), (-40, 0)], 16 / 9)
    assert any("tidak semua tokoh" in w for w in warn)


# ---------- endpoint resolve ----------
def layout_for(cid, **extra):
    return {"version": 2, "duration": 4, "camera": CAM, "actors": [{"character_id": cid, "body": "humanoid", "keys": [{"t": 0, "pos": [0, 0, 0]}]}],
            "props": [{"id": "meja1", "type": "table", "against": "north"}, {"id": "cangkir1", "type": "cup", "on": "meja1"}], **extra}


def test_resolve_endpoint_merges_set_and_scene_and_picks_environment(api):
    f, s, (cid,) = ready_scene(api)
    loc = api.get("/api/locations").json()[0]["id"]
    api.studio.db.execute("UPDATE locations SET set_layout = ? WHERE id = ?", (json.dumps({"version": 1, "bounds": [10, 8], "objects": [
        {"id": "lemari", "type": "shelf", "against": "west", "rot": [0, 0, 0], "scale": 1}]}), loc))
    api.studio.db.execute("UPDATE characters SET look = ? WHERE id = ?", (json.dumps({"body": "humanoid", "skin": "#c68642"}), cid))
    layout = layout_for(cid)
    layout["props"].append({"id": "kursi", "type": "chair", "near": "lemari"})                     # merujuk objek set
    r = api.post(f"/api/scenes/{s}/blockout/resolve", json={"layout": layout})
    assert r.status_code == 200, r.text
    body = r.json()
    ids = {x["id"]: x for x in body["props"]}
    assert ids["lemari"]["layer"] == "set" and ids["kursi"]["layer"] == "scene" and ids["cangkir1"]["pos"][1] == pytest.approx(0.75)
    assert body["bounds"] == [10, 8] and body["environment"]["time"] == "senja"                      # dari time_of_day adegan
    assert body["looks"][cid]["skin"] == "#c68642" and body["layout"]["version"] == 2
    api.studio.db.execute("UPDATE scenes SET blockout = ? WHERE id = ?", (json.dumps(layout), s))
    assert api.post(f"/api/scenes/{s}/blockout/resolve", json={}).json()["layout"]["props"][0]["id"] == "meja1"     # tersimpan


def test_resolve_endpoint_errors_and_isolation(api):
    f, s, (cid,) = ready_scene(api)
    assert api.post(f"/api/scenes/{s}/blockout/resolve", json={}).status_code == 404                   # belum ada susunan
    assert api.post(f"/api/scenes/{s}/blockout/resolve", json={"layout": layout_for("asing")}).status_code == 422
    assert api.post(f"/api/scenes/{s}/blockout/resolve", json={"layout": layout_for(cid)}, **hdr(mkws(api, "lain"))).status_code == 404
    put(api, s, blockout=layout_for(cid))
    assert api.post(f"/api/scenes/{s}/blockout/resolve", json={}).status_code == 200
