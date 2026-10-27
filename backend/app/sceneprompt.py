"""Prompt adegan (plan 08): modul murni tanpa DB/HTTP, terpisah dari editprompt.py (Edit Foto tidak disentuh).

Keyframe = satu panggilan edit gambar: gambar 1 = latar, gambar 2..n = tampilan tiap pemeran (spike plan 08: satu panggilan
untuk 1-2 pemeran menjaga latar, identitas, dan baju tanpa membawa background foto karakter).
Estimasi dan generate memakai fungsi yang sama, jadi jumlah gambar dan teksnya tidak bisa berbeda.
"""
MAX_DESC = 200   # deskripsi karakter/latar dipotong di prompt supaya total < 4000 karakter


def _clip(text: str | None, limit: int = MAX_DESC) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _head(scene: dict, cast: list[dict]) -> str:
    """Bagian yang dibaca model sebagai permintaan: aksi tiap pemeran, waktu, kamera, teks tambahan."""
    parts = [f"{c['name']}: {c['action'].strip()}." for c in cast if (c.get("action") or "").strip()]
    if (scene.get("time_of_day") or "").strip():
        parts.append(f"Time: {scene['time_of_day'].strip()}.")
    if (scene.get("camera") or "").strip():
        parts.append(f"Camera: {scene['camera'].strip()}.")
    if (scene.get("extra_prompt") or "").strip():
        parts.append(scene["extra_prompt"].strip())
    return " ".join(parts)


def keyframe_prompt(scene: dict, location: dict, cast: list[dict]) -> str:
    """cast: [{name, description, action, outfit_text}] berurutan sama dengan gambar 2..n; outfit_text hanya untuk tampilan tanpa gambar."""
    head = _head(scene, cast) or f"A still frame at {location['name']}."
    where = f" ({_clip(location.get('description'))})" if (location.get("description") or "").strip() else ""
    roles = [f"Image 1 is the LOCATION{where}: keep this place, its layout, light and mood."]
    for n, c in enumerate(cast, 2):
        who = f" ({_clip(c.get('description'))})" if (c.get("description") or "").strip() else ""
        keep = "face, hair, skin tone, body shape"
        if c.get("outfit_text"):
            outfit = f"{keep} exactly as in image {n}, but change the clothing to: {_clip(c['outfit_text'])}"
        else:
            outfit = f"{keep}, clothing and colors exactly as in image {n}"
        roles.append(f"Image {n} shows CHARACTER {c['name']}{who}: put only this person into the location of image 1 and ignore "
                     f"the background of image {n}. Keep their {outfit}.")
    if len(cast) > 1:
        roles.append("Do not swap the characters' faces or clothes.")
    return f"{head}\n---\n" + "\n".join(roles)


def video_prompt(scene: dict, cast: list[dict]) -> str:
    """Prompt video: gerakan saja; identitas sudah dibawa keyframe, jadi tanpa deskripsi panjang."""
    return _head(scene, cast) or "Natural motion; the scene comes alive."


def portrait_prompt(description: str) -> str:
    """Potret karakter dari deskripsi saja (plan 16). Nama sengaja tidak dipakai: model bisa menggambar teks/label dari nama."""
    return (f"Character design reference: {_clip(description, 800)}. Full body, standing, facing the camera, neutral relaxed pose, "
            "plain light grey studio background, even soft lighting, a single character, nothing in the background. No text, no labels, no watermark.")


def location_prompt(name: str, description: str | None) -> str:
    text = f"{name.strip()}. {_clip(description, 300)}".strip()
    return f"{text} No people. Cinematic wide establishing shot."
