"""Prompt gambar panel komik (plan 21), fungsi murni. Teks balon sengaja TIDAK dikirim: model gambar sering salah mengeja,
dan balon digambar sebagai overlay yang bisa diedit."""

STYLES = {"project": "comic book panel",
          "manga": "black-and-white manga panel with clean ink lines and screentone shading",
          "western": "full-color western comic book panel with bold ink outlines and cel shading",
          "webtoon": "full-color webtoon panel with clean line art and soft digital coloring"}
SHOTS = {"WS": "wide shot showing the whole surroundings", "MS": "medium shot from the waist up",
         "MCU": "medium close-up from the chest up", "CU": "close-up on the face", "ECU": "extreme close-up"}
ANGLES = {"eye": "eye-level camera", "low": "low angle looking up", "high": "high angle looking down",
          "overhead": "top-down overhead view", "dutch": "tilted dutch angle"}
NO_TEXT = ("No text, no lettering, no speech bubbles, no captions, no sound-effect words, no watermark. "
           "Leave some clear empty space near the top of the panel for dialogue balloons added later.")


def _with(desc: str | None) -> str:
    desc = (desc or "").strip()
    return f" ({desc[:400]})" if desc else ""


def build(panel: dict, characters: list[dict], location: dict | None, project_style: str = "") -> str:
    """characters: [{name, description, image_id|None}] berurutan; location: {name, description, image_id|None} atau None.
    Penomoran gambar mengikuti urutan input di Comic.plan: latar bergambar dulu, lalu karakter bergambar."""
    lines = [f"A single {STYLES[panel['comic_style']]}, {SHOTS[panel['shot']]}, {ANGLES[panel['angle']]}."]
    if project_style.strip():
        lines.append(f"Visual style: {project_style.strip().rstrip('.')}.")
    if panel["description"].strip():
        lines.append(f"Panel: {panel['description'].strip()}")
    n = 0
    if location and location.get("image_id"):
        n += 1
        lines.append(f"Image {n} is the LOCATION {location['name']}{_with(location.get('description'))}: draw the panel in this place, "
                     "keep its layout, light and mood.")
    elif location:
        lines.append(f"Setting: {location['name']}{_with(location.get('description'))}.")
    for c in characters:
        if c.get("image_id"):
            n += 1
            lines.append(f"Image {n} shows CHARACTER {c['name']}{_with(c.get('description'))}: keep their face, hair, skin tone, body shape, "
                         f"clothing and colors exactly; ignore the background of image {n}.")
        else:
            lines.append(f"CHARACTER {c['name']}{_with(c.get('description'))}.")
    if len(characters) > 1:
        lines.append("Do not swap the characters' faces or clothes.")
    lines.append(NO_TEXT)
    return "\n".join(lines)
