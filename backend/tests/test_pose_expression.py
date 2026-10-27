import base64
import io

import pytest
from PIL import Image

from app import editprompt
from app.editprompt import EditPlan, InputError, build_prompt, plan_inputs
from conftest import png_bytes

RED, GREEN, BLUE, YELLOW, CYAN, GRAY, PINK = (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255), (120, 120, 120), (255, 120, 200)
BIG = {"id": "x/big-edit", "architecture": {"input_modalities": ["text", "image"]},
       "supported_parameters": {"input_references": {"type": "range", "min": 0, "max": 8}}}


# ---------- fungsi murni ----------
def ids(entries):
    return [(e.image_id, e.transform, sorted(e.roles)) for e in entries]


def test_order_is_source_identity_pose_expression_references():
    sheet = [("s", "source"), ("f", "front"), ("t", "three_quarter")]
    got = plan_inputs("src", sheet, pose_id="p", expression_id="e", reference_ids=["r1", "r2"], max_inputs=10)
    assert [e.image_id for e in got] == ["src", "f", "t", "s", "p", "e", "r1", "r2"]   # sheet urut prioritas
    assert got[4].transform == "sketch" and got[4].roles == {"pose"}


def test_edited_image_is_never_sent_twice_and_duplicates_are_merged():
    got = plan_inputs("src", [("src", "source"), ("f", "front")], pose_id="p", reference_ids=["src", "p", "f", "x"], max_inputs=10)
    assert [e.image_id for e in got] == ["src", "f", "p", "x"]                         # sumber/pose/sheet tidak diulang di referensi
    both = plan_inputs("src", None, pose_id="p", pose_mode="original", expression_id="p", max_inputs=5)
    assert ids(both) == [("src", None, ["source"]), ("p", None, ["expression", "pose"])]   # satu gambar, dua peran
    sk = plan_inputs("src", [("p", "front")], pose_id="p", max_inputs=5)
    assert [(e.image_id, e.transform) for e in sk] == [("src", None), ("p", None), ("p", "sketch")]   # sketsa = gambar lain


@pytest.mark.parametrize("kw", [{"pose_id": "src"}, {"expression_id": "src"}, {"pose_mode": "aneh"}])
def test_invalid_roles_rejected(kw):
    with pytest.raises(InputError):
        plan_inputs("src", None, max_inputs=5, **kw)


def test_only_sheet_images_are_pruned_lowest_priority_first():
    sheet = [(n, n) for n in ("source", "front", "side", "three_quarter", "full_body", "custom")]
    got = plan_inputs("src", sheet, pose_id="p", expression_id="e", reference_ids=["r"], max_inputs=6)
    assert [e.image_id for e in got] == ["src", "front", "three_quarter", "p", "e", "r"]   # side, full_body, source, custom terpangkas
    with pytest.raises(InputError, match="maksimal 3"):
        plan_inputs("src", sheet, pose_id="p", expression_id="e", reference_ids=["r"], max_inputs=3)   # pose+ekspresi+ref tidak dibuang


def test_prompt_numbers_come_from_final_list():
    char = {"name": "Rina", "description": "bob hitam, jaket merah"}
    sheet = [("f", "front"), ("t", "three_quarter")]
    plan = EditPlan(plan_inputs("src", sheet, pose_id="p", expression_id="e", reference_ids=["r"], max_inputs=9), char)
    text = build_prompt("Ganti latar", plan)
    assert text.startswith("Ganti latar\n---\n")
    assert "Images 2-3 show the same character (Rina: bob hitam, jaket merah)" in text
    assert "Image 4 is a line-drawing POSE reference" in text
    assert "Image 5 is an EXPRESSION reference" in text and "Image 6 are additional references" in text
    assert "Do not change the character's identity." in text
    one = build_prompt("x", EditPlan(plan_inputs("src", [("f", "front")], max_inputs=5), char))
    assert "Image 2 show" in one and "Images 2-1" not in one


def test_plain_edit_prompt_is_untouched_and_text_only_adds_no_images():
    plain = EditPlan(plan_inputs("src", None, reference_ids=["r"], max_inputs=5))
    assert build_prompt("ganti latar", plain) == "ganti latar"
    only_text = EditPlan(plan_inputs("src", None, max_inputs=5), pose_text="hands on hips", expression_text="big smile")
    out = build_prompt("x", only_text)
    assert len(only_text.entries) == 1 and "Change the pose to: hands on hips." in out and "Change the facial expression to: big smile." in out


def test_text_limit_and_blank_text():
    assert editprompt.clean_text("   ", "pose") is None
    with pytest.raises(InputError):
        editprompt.clean_text("x" * 201, "pose")


def _png(img):
    buf = io.BytesIO(); img.save(buf, "PNG"); return buf.getvalue()


def test_pose_sketch_drops_color():
    img = Image.new("RGB", (80, 120), (200, 30, 30))
    img.paste((20, 20, 220), (20, 20, 60, 100))   # satu bentuk di atas latar
    out = Image.open(io.BytesIO(editprompt.make_pose_sketch(_png(img)))).convert("RGB")
    px = [out.getpixel((x, y)) for x in range(0, 80, 7) for y in range(0, 120, 9)]
    assert all(abs(r - g) < 3 and abs(g - b) < 3 for r, g, b in px)    # abu-abu: warna baju/kulit tidak ikut
    assert sum(1 for r, _, _ in px if r > 250) > len(px) * 0.6          # latar putih


# ---------- lewat API ----------
def up(api, color):
    r = api.post("/api/images", files={"file": ("a.png", png_bytes(color, (64, 48)), "image/png")})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def sent(fake):
    """Warna piksel tiap gambar yang dikirim ke provider, berurutan."""
    body = fake.last_json("/images")
    out = []
    for ref in body["input_references"]:
        data = base64.b64decode(ref["image_url"]["url"].split(",", 1)[1])
        out.append(Image.open(io.BytesIO(data)).convert("RGB").getpixel((5, 5)))
    return body, out


def provider_calls(fake):
    return len([r for r in fake.requests if r.method == "POST" and r.url.path.endswith("/images")])


@pytest.fixture
def big(api, monkeypatch):
    monkeypatch.setattr(api.studio, "image_models", lambda: [BIG])
    return BIG["id"]


def make_character(api, extra=("front", "side", "three_quarter", "full_body")):
    src = up(api, GRAY)
    char = api.post("/api/characters", json={"name": "Rina", "description": "bob hitam", "source_image_id": src}).json()
    colors = {"front": GREEN, "side": BLUE, "three_quarter": CYAN, "full_body": PINK}
    for label in extra:
        api.studio.add_character_image(char["id"], up(api, colors[label]), label)
    return char["id"]


def edit(api, image_id, model, **body):
    return api.post(f"/api/images/{image_id}/edit", json={"prompt": "ganti latar", "model": model, **body})


def test_payload_order_matches_prompt_numbers(api, fake, big):
    src, pose, expr, ref = up(api, RED), up(api, YELLOW), up(api, PINK), up(api, BLUE)
    cid = make_character(api, extra=("front", "three_quarter"))
    r = edit(api, src, big, character_id=cid, pose_image_id=pose, expression_image_id=expr, reference_image_ids=[ref])
    assert r.status_code == 200, r.text
    body, colors = sent(fake)
    # 1 sumber, 2-3 sheet (front, three_quarter), 4 sheet source (abu-abu), 5 sketsa pose (putih), 6 ekspresi, 7 referensi
    assert colors == [RED, GREEN, CYAN, GRAY, (255, 255, 255), PINK, BLUE]
    prompt = body["prompt"]
    assert "Images 2-4 show the same character (Rina: bob hitam)" in prompt
    assert "Image 5 is a line-drawing POSE reference" in prompt and "Image 6 is an EXPRESSION reference" in prompt
    assert "Image 7 are additional references" in prompt
    saved = r.json()[0]["prompt"]
    assert saved.startswith("ganti latar\n---\n") and saved == prompt           # teks user dulu, peran setelah pemisah


def test_character_lock_no_longer_drops_user_references(api, fake, big):
    """Regresi: dulu sheet dimasukkan lebih dulu lalu `[:4]` membuang referensi user diam-diam."""
    src, r1, r2 = up(api, RED), up(api, YELLOW), up(api, PINK)
    cid = make_character(api)                    # sheet 5 gambar
    assert edit(api, src, big, character_id=cid, reference_image_ids=[r1, r2]).status_code == 200
    _, colors = sent(fake)
    assert YELLOW in colors and PINK in colors and len(colors) == 8


def test_sheet_is_pruned_but_user_inputs_are_kept_and_hard_limit_rejects_before_provider(api, fake, monkeypatch):
    small = {**BIG, "supported_parameters": {"input_references": {"type": "range", "min": 0, "max": 5}}}
    monkeypatch.setattr(api.studio, "image_models", lambda: [small])
    src, pose, expr, ref = up(api, RED), up(api, YELLOW), up(api, PINK), up(api, BLUE)
    cid = make_character(api)
    assert edit(api, src, small["id"], character_id=cid, pose_image_id=pose, expression_image_id=expr,
                reference_image_ids=[ref]).status_code == 200
    _, colors = sent(fake)
    assert len(colors) == 5 and colors[0] == RED and colors[1] == GREEN and PINK in colors and BLUE in colors   # front dipertahankan
    before = provider_calls(fake)
    r = edit(api, src, small["id"], pose_image_id=pose, expression_image_id=expr, reference_image_ids=[ref, up(api, CYAN), up(api, GRAY)])
    assert r.status_code == 400 and "maksimal 5" in r.json()["detail"]
    assert provider_calls(fake) == before                                          # provider tidak dipanggil


def test_text_only_pose_and_expression_add_no_images(api, fake, big):
    src = up(api, RED)
    assert edit(api, src, big, pose_text="hands on hips", expression_text="big smile").status_code == 200
    body, colors = sent(fake)
    assert colors == [RED] and "Change the pose to: hands on hips." in body["prompt"]


def test_validation_errors(api, big):
    src, other = up(api, RED), up(api, BLUE)
    assert edit(api, src, big, pose_image_id=src).status_code == 400
    assert edit(api, src, big, pose_image_id="tidak-ada").status_code == 404
    assert edit(api, src, big, pose_text="x" * 201).status_code == 422
    api.delete(f"/api/images/{other}")
    assert edit(api, src, big, expression_image_id=other).status_code == 404        # gambar terhapus


def test_final_prompt_length_is_checked(api, big):
    src, pose = up(api, RED), up(api, YELLOW)
    r = api.post(f"/api/images/{src}/edit", json={"prompt": "y" * 3900, "model": big, "pose_image_id": pose})
    assert r.status_code == 400 and "terlalu panjang" in r.json()["detail"]


def test_sketch_preview_endpoint_returns_the_png_that_would_be_sent(api):
    pid = up(api, YELLOW)
    r = api.get(f"/api/images/{pid}/sketch")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).convert("RGB").getpixel((5, 5)) == (255, 255, 255)
    assert api.get("/api/images/tidak-ada/sketch").status_code == 404


def test_estimate_counts_same_inputs_as_generate(api, fake, big):
    src, pose, expr, ref = up(api, RED), up(api, YELLOW), up(api, PINK), up(api, BLUE)
    cid = make_character(api)
    body = {"kind": "image_edit", "model": big, "source_image_id": src, "character_id": cid, "pose_image_id": pose,
            "expression_image_id": expr, "reference_image_ids": [ref]}
    est = api.post("/api/estimate", json=body).json()
    assert edit(api, src, big, character_id=cid, pose_image_id=pose, expression_image_id=expr, reference_image_ids=[ref]).status_code == 200
    _, colors = sent(fake)
    # 9 kandidat (sumber + 5 sheet + pose + ekspresi + referensi) dipangkas ke batas model 8; estimasi dan generate sama-sama 8
    assert est["inputs"] == len(colors) == 8 and GRAY not in colors
    # klien lama (hanya jumlah) tetap jalan; masukan tak valid ditolak juga di estimasi
    assert api.post("/api/estimate", json={"kind": "image_edit", "model": big, "reference_count": 2}).status_code == 200
    assert api.post("/api/estimate", json={**body, "pose_image_id": src}).status_code == 400
