"""Spike plan 06 (BERBIAYA, batas keras $0,50): apakah gambar pose/ekspresi bisa mengubah pose tanpa mengubah karakter?

Pemakaian (kunci API dari environment, tidak pernah dicetak):
  models              daftar model gambar murah yang menerima input gambar (hanya baca, gratis)
  prep                siapkan gambar uji dari docs/spike/ (gratis)
  mkref MODEL         buat gambar referensi pose (pria, duduk, tangan di pinggang) dari foto pria yang ada
  run MODEL CASE      CASE: raw (pose dari gambar asli) | sketch (pose dari sketsa garis) | text (pose+ekspresi teks) | lock (sheet + pose asli)
Anggaran: SPIKE_CAP_USD (default 0.50). Sebelum tiap panggilan dicek terhadap batas atas estimator; biaya nyata dari usage.cost.
"""
import base64, io, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from PIL import Image, ImageFilter, ImageOps  # noqa: E402
from app import media, pricing  # noqa: E402
from app.openrouter import OpenRouterClient, OpenRouterError  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..", "docs", "spike")
D = os.environ["SPIKE_DIR"].rstrip("/") + "/"
CAP = float(os.getenv("SPIKE_CAP_USD", "0.50"))
STATE = D + "state.json"
c = OpenRouterClient(os.environ["OPENROUTER_API_KEY"], "https://openrouter.ai/api/v1")

IDENTITY = ("Image 1 provides the character's identity, outfit, background and lighting. Keep the person in image 1 exactly: "
            "face, hair, skin tone, body shape, clothing and colors.")
POSE_RAW = ("Image 2 is a POSE reference only: change the pose of the person in image 1 to match the body pose and gesture in image 2, "
            "even though it differs from image 1. Do NOT copy the identity, face, hair, clothing or colors of the person in image 2.")
POSE_SKETCH = ("Image 2 is a line-drawing POSE reference only: change the pose of the person in image 1 to match the body pose in the drawing, "
               "even though it differs from image 1. Keep everything else from image 1.")
LOCK = ("Images 2-3 show the same character from other angles: keep face, hair, skin tone, body shape, outfit and colors exactly as in them and image 1. "
        "Image 4 is a POSE reference only: change the pose of the person in image 1 to match it; ignore the identity, face, hair, clothing and colors of the person in image 4.")
TEXT = "Change the pose to: hands on hips, weight on one leg. Change the facial expression to: big open smile showing teeth."
GOAL = "Same woman, same clothes, same room. Only the pose and expression change."


def load():
    return json.load(open(STATE)) if os.path.exists(STATE) else {"spent": 0.0, "runs": {}}


def save(s):
    json.dump(s, open(STATE, "w"), indent=1)


def b64(img):
    buf = io.BytesIO(); img.save(buf, "PNG")
    return media.to_data_url(buf.getvalue())


def sketch(img):
    g = ImageOps.autocontrast(img.convert("L")).filter(ImageFilter.FIND_EDGES)
    return ImageOps.invert(ImageOps.autocontrast(g)).convert("RGB")


def panels():
    sheet = Image.open(f"{ROOT}/03-character-sheet.png").convert("RGB")
    w = sheet.width // 5
    views = [sheet.crop((i * w, 0, (i + 1) * w, sheet.height)) for i in range(5)]
    anchor = Image.open(f"{ROOT}/03-anchor-frame.png").convert("RGB")
    third = anchor.width // 3
    man = anchor.crop((0, 0, third, anchor.height))
    woman_room = anchor.crop((third, 0, 2 * third, anchor.height))
    return views, man, woman_room


def pick_models():
    out = []
    for m in c.list_all_image_models():
        if "image" not in (m.get("architecture", {}).get("input_modalities") or []):
            continue
        try:
            eps = c.get_image_endpoints(m["id"])
        except OpenRouterError:
            continue
        e = pricing.estimate_image(eps, n_inputs=2)
        if e.confidence != "unknown":
            out.append((e.high, m["id"], e.confidence, m))
    return sorted(out, key=lambda x: x[0])


def est_high(model, n_inputs):
    return pricing.estimate_image(c.get_image_endpoints(model), n_inputs=n_inputs).high


def call(model, tag, prompt, imgs):
    s = load()
    need = est_high(model, len(imgs))
    if s["spent"] + need > CAP:
        sys.exit(f"STOP: anggaran ${CAP} akan terlampaui (terpakai {s['spent']:.4f} + batas atas {need:.4f})")
    print(f"{tag}: kirim {len(imgs)} gambar ke {model} (batas atas ${need:.4f}, terpakai ${s['spent']:.4f})", flush=True)
    opts = {"quality": os.environ["SPIKE_QUALITY"]} if os.getenv("SPIKE_QUALITY") else {}
    resp = c.edit_image(model, prompt, [b64(i) for i in imgs], **opts)
    cost = (resp.get("usage") or {}).get("cost") or 0
    s["spent"] += cost
    data = (resp.get("data") or [{}])[0].get("b64_json")
    s["runs"][tag] = {"model": model, "cost": cost, "inputs": len(imgs), "has_image": bool(data), "prompt": prompt}
    save(s)
    if data:
        open(D + f"{tag}.png", "wb").write(base64.b64decode(data))
    print(f"{tag}: biaya ${cost} total ${s['spent']:.4f} gambar={'ya' if data else 'TIDAK ADA'}")


cmd = sys.argv[1]
if cmd == "models":
    for high, mid, conf, _ in pick_models()[:12]:
        print(f"{high:8.4f}  {conf:8s}  {mid}")
elif cmd == "prep":
    views, man, room = panels()
    for name, im in {"woman": room, "man": man, "sheet_front": views[1], "sheet_34": views[3]}.items():
        im.save(D + f"{name}.png")
    sketch(man).save(D + "man_sketch.png")
    print("siap:", sorted(f for f in os.listdir(D) if f.endswith(".png")))
elif cmd == "mkref":
    model = sys.argv[2]
    call(model, "ref_" + model.replace("/", "_"), "Same man, same hoodie and jeans, same wall. Now he sits on a stool with one hand on his hip "
         "and the other raised, laughing.", [Image.open(D + "man.png")])
elif cmd == "run":
    model, case = sys.argv[2], sys.argv[3]
    tag = f"{case}_{model.replace('/', '_')}{os.getenv('SPIKE_SUFFIX', '')}"   # SPIKE_SUFFIX=_r2 untuk ulangan
    woman, ref = Image.open(D + "woman.png"), Image.open(D + "ref.png")
    if case == "raw":
        call(model, tag, f"{IDENTITY}\n{POSE_RAW}\n{GOAL}", [woman, ref])
    elif case == "sketch":
        call(model, tag, f"{IDENTITY}\n{POSE_SKETCH}\n{GOAL}", [woman, sketch(ref)])
    elif case == "text":
        call(model, tag, f"{IDENTITY}\n{TEXT}\n{GOAL}", [woman])
    elif case == "lock":
        call(model, tag, f"{IDENTITY}\n{LOCK}\n{GOAL}", [woman, Image.open(D + "sheet_front.png"), Image.open(D + "sheet_34.png"), ref])
    else:
        sys.exit("CASE tidak dikenal")
