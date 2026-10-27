"""Referensi pose/ekspresi pada edit foto (plan 06).

Modul murni (tanpa DB/HTTP): menentukan gambar apa yang dikirim ke model dan dalam urutan apa
(`plan_inputs`), lalu menulis prompt berperan yang nomornya diturunkan dari daftar final itu
(`build_prompt`). Estimasi biaya dan generate memakai fungsi yang sama, jadi jumlah gambar tidak bisa berbeda.
"""
import io
from dataclasses import dataclass, field

from PIL import Image, ImageFilter, ImageOps

MAX_TEXT = 200
# Prioritas gambar sheet: yang paling penting untuk identitas dulu; dipangkas dari belakang bila melewati batas model.
SHEET_PRIORITY = ["front", "three_quarter", "side", "full_body", "source", "custom"]
POSE_MODES = ("sketch", "original")


class InputError(ValueError):
    """Masukan tidak valid (pesan untuk user)."""


@dataclass
class Entry:
    image_id: str
    transform: str | None = None                      # None | "sketch" (sketsa garis dibuat saat kirim)
    roles: set[str] = field(default_factory=set)      # source | identity | pose | expression | reference
    label: str | None = None                          # label sheet bila dari karakter


@dataclass
class EditPlan:
    entries: list[Entry]                              # urutan kirim; entries[0] = gambar sumber
    character: dict | None = None
    pose_text: str | None = None
    expression_text: str | None = None


def clean_text(value: str | None, what: str) -> str | None:
    value = (value or "").strip()
    if len(value) > MAX_TEXT:
        raise InputError(f"teks {what} maksimal {MAX_TEXT} karakter")
    return value or None


def plan_inputs(source_id: str, sheet: list[tuple[str, str]] | None, *, pose_id: str | None = None,
                pose_mode: str = "sketch", expression_id: str | None = None,
                reference_ids: list[str] | tuple[str, ...] = (), max_inputs: int = 5) -> list[Entry]:
    """Urutan: sumber, identitas (sheet), pose, ekspresi, referensi lain. Yang dipangkas hanya sheet (prioritas terendah dulu)."""
    if pose_mode not in POSE_MODES:
        raise InputError(f"pose_mode harus salah satu dari {POSE_MODES}")
    if pose_id and pose_id == source_id:
        raise InputError("gambar pose sama dengan gambar sumber; pilih gambar lain")
    if expression_id and expression_id == source_id:
        raise InputError("gambar ekspresi sama dengan gambar sumber; pilih gambar lain")
    entries = [Entry(source_id, roles={"source"})]
    index: dict[tuple[str, str | None], Entry] = {(source_id, None): entries[0]}

    def add(image_id: str, transform: str | None, role: str, label: str | None = None) -> None:
        key = (image_id, transform)
        if key in index:
            if role != "reference":      # referensi umum yang sudah punya peran lain tidak dikirim dua kali
                index[key].roles.add(role)
            return
        entry = Entry(image_id, transform, {role}, label)
        entries.append(entry); index[key] = entry

    ordered = sorted(sheet or [], key=lambda s: SHEET_PRIORITY.index(s[1]) if s[1] in SHEET_PRIORITY else len(SHEET_PRIORITY))
    for image_id, label in ordered:
        if image_id != source_id:        # gambar yang diedit tidak dikirim dua kali
            add(image_id, None, "identity", label)
    if pose_id:
        add(pose_id, "sketch" if pose_mode == "sketch" else None, "pose")
    if expression_id:
        add(expression_id, None, "expression")
    roled = {source_id, pose_id, expression_id}   # referensi umum yang sama dengan gambar berperan dibuang (grill 06 nomor 6)
    for rid in reference_ids:
        if rid not in roled:
            add(rid, None, "reference")

    while len(entries) > max_inputs:     # pangkas sheet dari prioritas terendah; pose/ekspresi/referensi user tidak pernah dibuang
        droppable = [e for e in entries if e.roles == {"identity"}]
        if not droppable:
            raise InputError(f"terlalu banyak gambar input ({len(entries)}): model menerima maksimal {max_inputs}; "
                             "kurangi referensi atau pilih model yang menerima lebih banyak gambar")
        entries.remove(droppable[-1])
    return entries


def _imgs(nums: list[int]) -> str:
    if len(nums) == 1:
        return f"Image {nums[0]}"
    if nums == list(range(nums[0], nums[-1] + 1)):
        return f"Images {nums[0]}-{nums[-1]}"
    return "Images " + ", ".join(map(str, nums))


def build_prompt(user_prompt: str, plan: EditPlan) -> str:
    """Prompt pengguna dulu, lalu pemisah `---` dan peran tiap gambar (nomor dari urutan final)."""
    nums = {id(e): i + 1 for i, e in enumerate(plan.entries)}
    identity = [e for e in plan.entries if "identity" in e.roles and not e.roles & {"pose", "expression"}]
    posed = [e for e in plan.entries if "pose" in e.roles]
    exprs = [e for e in plan.entries if "expression" in e.roles and "pose" not in e.roles]
    others = [e for e in plan.entries if e.roles == {"reference"}]
    if not (plan.character or identity or posed or exprs or plan.pose_text or plan.expression_text):
        return user_prompt               # edit biasa: perilaku lama, prompt tidak diubah

    lines = ["Image 1 provides the character's identity, outfit, background and lighting. Keep the person in image 1 exactly: "
             "face, hair, skin tone, body shape, clothing and colors."]
    if identity:
        who = f" ({plan.character['name']}: {plan.character['description']})" if plan.character else ""
        lines.append(f"{_imgs([nums[id(e)] for e in identity])} show the same character{who} from other angles: keep face, hair, "
                     "skin tone, body shape, outfit and colors exactly as in them and image 1.")
    for e in posed:
        n = nums[id(e)]
        both = "expression" in e.roles
        if e.transform == "sketch":
            lines.append(f"Image {n} is a line-drawing POSE reference only: change the pose of the person in image 1 to match the body "
                         "pose in the drawing, even though it differs from image 1. Keep everything else from image 1.")
        elif both:
            lines.append(f"Image {n} is a POSE and EXPRESSION reference only: change the pose of the person in image 1 to match the body "
                         f"pose and gesture in image {n} and copy the facial expression, even though they differ from image 1. "
                         "Do NOT copy the identity, face shape, hair, clothing or colors of the person in it.")
        else:
            lines.append(f"Image {n} is a POSE reference only: change the pose of the person in image 1 to match the body pose and "
                         f"gesture in image {n}, even though it differs from image 1. Do NOT copy the identity, face, hair, clothing "
                         "or colors of the person in it.")
    for e in exprs:
        n = nums[id(e)]
        lines.append(f"Image {n} is an EXPRESSION reference only: change the facial expression of the person in image 1 to match it. "
                     f"Ignore everything else in image {n} (identity, pose, clothing, colors).")
    if others:
        lines.append(f"{_imgs([nums[id(e)] for e in others])} are additional references (style, props, background); "
                     "use them only as far as the request mentions them.")
    if plan.pose_text:
        lines.append(f"Change the pose to: {plan.pose_text}.")
    if plan.expression_text:
        lines.append(f"Change the facial expression to: {plan.expression_text}.")
    lines.append("Do not change the character's identity.")
    return f"{user_prompt}\n---\n" + "\n".join(lines)


def make_pose_sketch(png: bytes) -> bytes:
    """Sketsa garis dari gambar pose (PIL saja, deterministik): membuang warna/wajah/baju, menyisakan bentuk tubuh."""
    img = Image.open(io.BytesIO(png)).convert("L")
    edges = ImageOps.autocontrast(ImageOps.autocontrast(img).filter(ImageFilter.FIND_EDGES))
    out = io.BytesIO()
    ImageOps.invert(edges).convert("RGB").save(out, "PNG")
    return out.getvalue()


def split_roles(stored_prompt: str) -> tuple[str, str | None]:
    """Prompt tersimpan -> (teks pengguna, bagian peran atau None)."""
    head, sep, tail = stored_prompt.partition("\n---\n")
    return (head, tail) if sep else (stored_prompt, None)
