"""Spike plan 08 (BERBIAYA, batas keras $0,50): bisakah keyframe adegan disusun dari latar + karakter?

Pertanyaan: (a) model gambar mau membuat latar dari teks saja? (b) satu karakter dimasukkan ke gambar latar tanpa mengubah wajah/baju
dan tanpa membawa background fotonya? (c) dua karakter: sekaligus (satu panggilan) atau bertahap (satu per karakter)?

Pemakaian (kunci API dari environment, tidak pernah dicetak; SPIKE_DIR = folder kerja sementara):
  models              model gambar murah (hanya baca, gratis) + cek estimator untuk 0 input
  prep                siapkan gambar uji dari docs/spike/03-anchor-frame.png (gratis)
  loc MODEL           (a) latar dari teks saja, tanpa gambar input
  one MODEL           (b) latar + 1 karakter (butuh loc_<MODEL>.png, atau loc.png bila ada)
  both MODEL          (c) latar + 2 karakter sekaligus
  step MODEL          (c) bertahap: hasil one + karakter ke-2 (+ karakter 1 sebagai pengunci identitas)
Anggaran: SPIKE_CAP_USD (default 0.50). Sebelum tiap panggilan dicek terhadap batas atas estimator; biaya nyata dari usage.cost.
"""
import base64, io, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from PIL import Image  # noqa: E402
from app import media, pricing  # noqa: E402
from app.openrouter import OpenRouterClient, OpenRouterError  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..", "docs", "spike")
D = os.environ["SPIKE_DIR"].rstrip("/") + "/"
CAP = float(os.getenv("SPIKE_CAP_USD", "0.50"))
STATE = D + "state.json"
c = OpenRouterClient(os.environ["OPENROUTER_API_KEY"], "https://openrouter.ai/api/v1")

LOC_TEXT = ("A narrow rice-field embankment at dusk, misty green mountains in the distance, a small bamboo hut on the right, "
            "warm orange light. No people. Cinematic wide shot.")
ONE = ("Image 1 is the LOCATION: keep this place, its layout, light and mood. Image 2 shows the CHARACTER (a woman): put only this person "
       "into the location of image 1 and ignore the background of image 2. Keep her face, hair, skin tone, body shape, clothing and colors "
       "exactly as in image 2. Action: she walks along the embankment toward the camera. Time: dusk. Camera: medium wide shot.")
BOTH = ("Image 1 is the LOCATION: keep this place, its layout, light and mood. Image 2 shows CHARACTER A (a woman) and image 3 shows "
        "CHARACTER B (a man). Put only these two people into the location of image 1 and ignore the backgrounds of images 2 and 3. "
        "Keep each person's face, hair, skin tone, body shape, clothing and colors exactly as in their own image; do not swap their faces "
        "or clothes. Action: the woman walks ahead toward the camera, the man follows behind her laughing. Time: dusk. Camera: medium wide shot.")
STEP2 = ("Image 1 is the current scene: keep it exactly, including the woman in it (image 3 shows her again for reference). Image 2 shows "
         "CHARACTER B (a man): add only this person to the scene, walking behind the woman, laughing, and ignore the background of image 2. "
         "Keep his face, hair, skin tone, body shape, clothing and colors exactly as in image 2, and keep the woman unchanged.")


def load():
    return json.load(open(STATE)) if os.path.exists(STATE) else {"spent": 0.0, "runs": {}}


def save(s):
    json.dump(s, open(STATE, "w"), indent=1)


def b64(img):
    buf = io.BytesIO(); img.save(buf, "PNG")
    return media.to_data_url(buf.getvalue())


def est_high(model, n_inputs):
    return pricing.estimate_image(c.get_image_endpoints(model), n_inputs=n_inputs).high


def call(model, tag, prompt, imgs):
    s = load()
    need = est_high(model, len(imgs))
    if s["spent"] + need > CAP:
        sys.exit(f"STOP: anggaran ${CAP} akan terlampaui (terpakai {s['spent']:.4f} + batas atas {need:.4f})")
    print(f"{tag}: kirim {len(imgs)} gambar ke {model} (batas atas ${need:.4f}, terpakai ${s['spent']:.4f})", flush=True)
    opts = {"quality": os.environ["SPIKE_QUALITY"]} if os.getenv("SPIKE_QUALITY") else {}
    if os.getenv("SPIKE_ASPECT"):
        opts["aspect_ratio"] = os.environ["SPIKE_ASPECT"]
    tag += os.getenv("SPIKE_SUFFIX", "")
    if imgs:
        resp = c.edit_image(model, prompt, [b64(i) for i in imgs], **opts)
    else:   # tanpa input_references sama sekali
        resp = c._request("POST", "/images", json={"model": model, "prompt": prompt, **opts}).json()
    cost = (resp.get("usage") or {}).get("cost") or 0
    s["spent"] += cost
    data = (resp.get("data") or [{}])[0].get("b64_json")
    s["runs"][tag] = {"model": model, "cost": cost, "inputs": len(imgs), "has_image": bool(data)}
    save(s)
    if data:
        open(D + f"{tag}.png", "wb").write(base64.b64decode(data))
    print(f"{tag}: biaya ${cost} total ${s['spent']:.4f} gambar={'ya' if data else 'TIDAK ADA'}", flush=True)


def slug(model):
    return model.replace("/", "_")


cmd = sys.argv[1]
if cmd == "models":
    for m in c.list_all_image_models():
        if "image" not in (m.get("architecture", {}).get("input_modalities") or []):
            continue
        try:
            eps = c.get_image_endpoints(m["id"])
        except OpenRouterError:
            continue
        e0, e3 = pricing.estimate_image(eps, n_inputs=0), pricing.estimate_image(eps, n_inputs=3)
        if e3.confidence != "unknown":
            print(f"{e3.high:8.4f} (0 input: {e0.high:.4f} {e0.confidence})  {e3.confidence:8s}  {m['id']}")
elif cmd == "prep":
    anchor = Image.open(f"{ROOT}/03-anchor-frame.png").convert("RGB")
    third = anchor.width // 3
    anchor.crop((0, 0, third, anchor.height)).save(D + "man.png")
    anchor.crop((third, 0, 2 * third, anchor.height)).save(D + "woman.png")
    print("siap:", sorted(f for f in os.listdir(D) if f.endswith(".png")))
elif cmd == "loc":
    call(sys.argv[2], "loc_" + slug(sys.argv[2]), LOC_TEXT, [])
elif cmd in ("one", "both", "step"):
    model = sys.argv[2]
    loc = Image.open(D + ("loc.png" if os.path.exists(D + "loc.png") else f"loc_{slug(model)}.png"))
    woman, man = Image.open(D + "woman.png"), Image.open(D + "man.png")
    if cmd == "one":
        call(model, "one_" + slug(model), ONE, [loc, woman])
    elif cmd == "both":
        call(model, "both_" + slug(model), BOTH, [loc, woman, man])
    else:
        call(model, "step2_" + slug(model), STEP2, [Image.open(D + f"one_{slug(model)}.png"), man, woman])
