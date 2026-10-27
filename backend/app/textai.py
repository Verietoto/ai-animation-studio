"""Panggilan model teks yang berbiaya (plan 14/15/17): katalog model yang disaring, estimasi, otorisasi, pencatatan biaya, JSON.

Satu jalur untuk susunan 3D, naskah, pecah naskah, dan penampilan/set. Biaya selalu masuk `text_jobs` (dan anggaran harian), balasan
rusak tetap tercatat berbiaya, dan model dipilih per permintaan (divalidasi server terhadap katalog yang sama dengan yang ditampilkan UI).
"""
import json
import time
import uuid

from . import pricing
from .db import now
from .openrouter import OpenRouterError
from .service import ServiceError

MIN_CONTEXT = 32_000            # token; di bawah ini tidak muat untuk naskah/pecah naskah
EXPENSIVE_OUT_PER_M = 20.0      # USD per juta token keluaran; di atasnya diberi tanda "mahal"
RECOMMENDED: dict[str, str] = {}   # id model -> alasan singkat; diisi dari hasil eval (scripts/eval_text_models.py)
PLACEHOLDERS = ("", "-", "teks")   # nilai `model` lama dari klien; berarti "pakai bawaan"


def _per_m(value) -> float | None:
    try:
        v = float(value) * 1e6
    except (TypeError, ValueError):
        return None
    return v if v >= 0 else None   # harga negatif = placeholder router otomatis, bukan harga


def catalog(st) -> list[dict]:
    """Model teks yang layak dipilih (cache 5 menit): keluaran teks, mendukung response_format, harga jelas, konteks cukup."""
    if st._text_catalog and time.time() - st._text_catalog[0] < 300:
        return st._text_catalog[1]
    try:
        models = st.client.list_models()
    except OpenRouterError as exc:
        raise ServiceError(str(exc), 502) from exc
    out = []
    for m in models:
        arch, params = m.get("architecture") or {}, m.get("supported_parameters") or []
        mid = m.get("id") or ""
        if (arch.get("output_modalities") != ["text"] or "text" not in (arch.get("input_modalities") or [])
                or "response_format" not in params or mid.endswith((":free", ":batch")) or (m.get("context_length") or 0) < MIN_CONTEXT):
            continue
        p_in, p_out = _per_m((m.get("pricing") or {}).get("prompt")), _per_m((m.get("pricing") or {}).get("completion"))
        if p_in is None or p_out is None:
            continue
        out.append({"id": mid, "name": m.get("name") or mid, "prompt_per_m": round(p_in, 4), "completion_per_m": round(p_out, 4),
                    "context": m.get("context_length"), "structured": "structured_outputs" in params, "reasoning": "reasoning" in params,
                    "vision": "image" in (arch.get("input_modalities") or []), "expensive": p_out > EXPENSIVE_OUT_PER_M,
                    "recommended": mid in RECOMMENDED, "note": RECOMMENDED.get(mid)})
    out.sort(key=lambda r: (not r["recommended"], r["expensive"], r["completion_per_m"]))
    st._text_catalog = (time.time(), out)
    return out


def default_model(st) -> str:
    return st.s.blockout_model


def info(st, model: str | None) -> dict:
    """Metadata model teks terpilih; tidak ada di katalog (tak dikenal, harga negatif, konteks kecil, tanpa JSON) -> 422 sebelum biaya."""
    model = default_model(st) if (model or "").strip() in PLACEHOLDERS else model
    found = next((m for m in catalog(st) if m["id"] == model), None)
    if found is None:
        raise ServiceError(f"model teks tidak tersedia: {model} (tidak dikenal, harga tidak jelas, konteks < {MIN_CONTEXT // 1000} ribu, "
                           "atau tanpa keluaran JSON)", 422)
    return found


def estimate(st, system: str, user: str, max_out: int, min_out: int = 2000, model: str | None = None) -> pricing.Estimate:
    meta = info(st, model)
    p_in, p_out = meta["prompt_per_m"] / 1e6, meta["completion_per_m"] / 1e6
    tokens_in = (len(system) + len(user)) / 3   # kasar: 1 token ~ 3 karakter
    return pricing.Estimate(tokens_in * p_in + min(min_out, max_out) * p_out, tokens_in * p_in + max_out * p_out, "formula",
                            [f"{meta['id']}: ~{tokens_in:.0f} token masuk + maks {max_out} token keluar"])


def parse_json(text: str) -> dict:
    """JSON toleran: buang pagar kode, lalu ambil objek seimbang pertama bila ada teks pengantar/penutup."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except ValueError:
        start = text.find("{")
        if start < 0:
            raise
        depth, in_str, esc, data = 0, False, False, None
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    data = json.loads(text[start:i + 1])
                    break
        if data is None:
            raise ValueError("objek JSON tidak lengkap")
    if not isinstance(data, dict):
        raise ValueError("bukan objek")
    return data


def _call(st, meta: dict, system: str, user: str, max_tokens: int, schema: dict | None) -> dict:
    """Skema ketat hanya untuk model yang mendukungnya; bila penyedia menolak karena skema, ulang SEKALI dengan json_object."""
    use = schema if (schema and meta["structured"]) else None
    try:
        return st.client.chat_json(meta["id"], system, user, max_tokens, schema=use, reasoning=meta["reasoning"])
    except OpenRouterError as exc:
        if use and exc.status in (400, 404, 422):
            try:
                return st.client.chat_json(meta["id"], system, user, max_tokens, schema=None, reasoning=meta["reasoning"])
            except OpenRouterError as exc2:
                raise ServiceError(str(exc2), 502) from exc2
        raise ServiceError(str(exc), 502) from exc


def ask(st, kind: str, system: str, user: str, max_tokens: int, est: pricing.Estimate, ws: str,
        confirmed_cost: float | None, accept_unknown_cost: bool, scene_id: str | None = None, model: str | None = None,
        schema: dict | None = None) -> tuple[dict, float | None]:
    """Otorisasi biaya, panggil model, catat biaya SEBELUM parsing. Pemanggil memegang `st._lock`."""
    meta = info(st, model)
    st.authorize(est, confirmed_cost, accept_unknown_cost)
    resp = _call(st, meta, system, user, max_tokens, schema)
    cost = (resp.get("usage") or {}).get("cost")
    st.db.insert("text_jobs", {"id": uuid.uuid4().hex, "kind": kind, "model": meta["id"], "cost": cost, "estimated_cost": est.high,
                               "scene_id": scene_id, "workspace_id": ws, "created_at": now()})
    try:
        choice = resp["choices"][0]
        content = ((choice.get("message") or {}).get("content") or "").strip()
    except (KeyError, IndexError, AttributeError):
        raise ServiceError("AI mengembalikan jawaban yang tidak bisa dibaca; coba lagi atau pilih model lain", 502) from None
    if not content:
        if choice.get("finish_reason") == "length":
            raise ServiceError(f"{meta['id']} kehabisan token (kemungkinan terpakai untuk berpikir) sehingga jawabannya kosong; "
                               "pilih model lain. Biaya tetap tercatat.", 502)
        raise ServiceError(f"{meta['id']} mengembalikan jawaban kosong; pilih model lain", 502)
    try:
        return parse_json(content), cost
    except ValueError:
        raise ServiceError(f"{meta['id']} tidak menghasilkan JSON yang bisa dibaca; coba lagi atau pilih model lain", 502) from None
