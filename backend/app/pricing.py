"""Estimator biaya sebelum generate (plan 04).

Sumber harga: `pricing_skus` dari GET /videos/models dan baris `pricing` dari
GET /images/models/{id}/endpoints. Satuan tidak seragam, jadi SKU yang tidak dikenal
membuat hasil `unknown` (tidak menebak). Satuan:
  cents_*            -> sen (dibagi 100)
  duration_seconds*  -> USD per detik
  video_tokens*      -> USD per token video (token = lebar x tinggi x 24 fps x detik / 1024)
"""
from dataclasses import dataclass, field

TOKEN_FPS = 24
FORMULA_MARGIN = 1.10          # rumus piksel -> token belum terbukti pada tagihan nyata
HISTORY_MARGIN = 1.5
IMAGE_OUTPUT_TOKENS_CEILING = 4500   # gpt-image-2 high 16:9 ~4000 token; Gemini 4K ~2000
IMAGE_INPUT_TOKENS_PER_IMAGE = 2000  # terukur ~1040 untuk 512x512; batas atas konservatif
SHORT_SIDE = {"480p": 480, "720p": 720, "768p": 768, "1080p": 1080, "1K": 1024, "2K": 1440, "4K": 2160}
MEGAPIXELS = {"512": 0.26, "768": 0.59, "1K": 1.05, "1.5K": 2.36, "2K": 4.19, "4K": 16.78}


@dataclass
class Estimate:
    low: float
    high: float
    confidence: str            # exact | formula | bound | history | unknown
    basis: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"low": round(self.low, 6), "high": round(self.high, 6),
                "confidence": self.confidence, "basis": self.basis}


UNKNOWN = Estimate(0.0, 0.0, "unknown")


def unknown(reason: str) -> Estimate:
    return Estimate(0.0, 0.0, "unknown", [reason])


def _usd(skus: dict, key: str) -> float | None:
    if key not in skus:
        return None
    value = float(skus[key])
    return value / 100 if "cents" in key else value


def _first(skus: dict, keys: list[str]) -> tuple[float, str] | None:
    for key in keys:
        value = _usd(skus, key)
        if value is not None:
            return value, key
    return None


def _per_second(skus: dict, res: str | None, audio: bool, mode: str) -> tuple[float, str] | None:
    keys: list[str] = []
    r = res.lower() if res else None
    if r:
        if audio:   # tarif dengan suara harus menang atas SKU i2v tanpa suara (Kling)
            keys += [f"duration_seconds_with_audio_{r}", "duration_seconds_with_audio"]
        if mode == "i2v":
            keys.append(f"image_to_video_duration_seconds_{r}")
        keys.append(f"duration_seconds_{'with' if audio else 'without'}_audio_{r}")
        keys += [f"duration_seconds_{r}", f"cents_per_video_output_second_{r}", f"cents_per_second_output_{r}"]
        if mode == "i2v":
            keys.append(f"text_to_video_duration_seconds_{r}")   # Wan 2.6: tidak ada SKU i2v 480p
    keys.append(f"duration_seconds_{'with' if audio else 'without'}_audio")
    if audio:
        keys.append("duration_seconds")   # model tanpa SKU "with_audio" tidak menaikkan tarif
    keys += ["duration_seconds", "cents_per_second_output"]
    return _first(skus, keys)


def _token_rate(skus: dict, res: str | None, audio: bool, video_input: bool) -> tuple[float, str] | None:
    suffix = {"4K": "_4k", "1080p": "_1080p"}.get(res or "", "")
    keys = []
    if video_input:
        keys += [f"video_tokens{suffix}_with_video_input", "video_tokens_with_video_input"]
    if not audio:
        keys.append("video_tokens_without_audio")
    keys += [f"video_tokens{suffix}", "video_tokens"]
    return _first(skus, keys)


def _pixels(res: str, aspect_ratio: str | None) -> float:
    short = SHORT_SIDE[res]
    ratio = 16 / 9
    if aspect_ratio and ":" in aspect_ratio:
        a, b = (float(x) for x in aspect_ratio.split(":", 1))
        ratio = max(a, b) / min(a, b)
    return short * short * ratio


def estimate_video(info: dict, *, duration: int | None, resolution: str | None, audio: bool,
                   aspect_ratio: str | None = None, mode: str = "i2v", image_inputs: int = 0,
                   reference_images: int = 0, video_input_seconds: float = 0.0) -> Estimate:
    skus = info.get("pricing_skus") or {}
    if not skus:
        return unknown("model tanpa data harga")
    if mode == "edit" and video_input_seconds:
        durations = [video_input_seconds]
    elif duration:
        durations = [duration]
    elif info.get("supported_durations"):
        durations = [min(info["supported_durations"]), max(info["supported_durations"])]
    else:
        return unknown("durasi tidak diketahui")
    resolutions = [resolution] if resolution else (info.get("supported_resolutions") or [None])
    if "cents_per_megapixel_second_precise" in skus:
        return unknown("harga per megapiksel-detik tidak didukung estimator")

    totals: list[float] = []
    confidence = "exact"
    basis: list[str] = []
    for res in resolutions:
        rate = _per_second(skus, res, audio, mode)
        for dur in (durations[0], durations[-1]):
            if rate is not None:
                total = rate[0] * dur
                basis.append(f"{rate[1]} x {dur}s") if (res, dur) == (resolutions[0], durations[0]) else None
            else:
                token_rate = _token_rate(skus, res, audio, video_input_seconds > 0)
                if token_rate is None or res is None or res not in SHORT_SIDE:
                    return unknown(f"tidak ada SKU harga yang cocok untuk resolusi {res}")
                tokens = _pixels(res, aspect_ratio) * TOKEN_FPS * dur / 1024
                if video_input_seconds:
                    tokens += _pixels(res, aspect_ratio) * TOKEN_FPS * video_input_seconds / 1024
                total = tokens * token_rate[0] * FORMULA_MARGIN
                confidence = "formula"
                if (res, dur) == (resolutions[0], durations[0]):
                    basis.append(f"{token_rate[1]} x {tokens:,.0f} token (+{int((FORMULA_MARGIN - 1) * 100)}% margin)")
            totals.append(total)

    extra = 0.0
    if image_inputs and (v := _usd(skus, "cents_per_image_input")) is not None:
        extra += v * image_inputs
        basis.append(f"{image_inputs} gambar input x ${v}")
    if reference_images:
        r = _first(skus, ["reference_images", "reference_input_images"])
        if r:
            extra += r[0] * reference_images
            basis.append(f"{reference_images} gambar referensi x ${r[0]}")
    minimum = _usd(skus, "minimum_cents_per_generation") or 0.0
    low, high = max(min(totals) + extra, minimum), max(max(totals) + extra, minimum)
    if minimum and low == minimum:
        basis.append(f"minimum per generasi ${minimum}")
    basis = list(dict.fromkeys(basis))   # buang baris dasar ganda (rentang durasi/resolusi)
    return Estimate(low, high, confidence, basis)


def estimate_image(endpoints: list[dict], *, n_outputs: int = 1, n_inputs: int = 0,
                   resolution: str | None = None, history: list[float] | None = None) -> Estimate:
    """endpoints: daftar `endpoints[]` dari /images/models/{id}/endpoints (tiap provider punya `pricing`)."""
    if not endpoints:
        return unknown("model tanpa data harga")
    lows, highs, confidences, basis = [], [], [], []
    for ep in endpoints:
        rows = {(p["billable"], p.get("variant")): p for p in ep.get("pricing", [])}
        out = next((p for (b, _), p in rows.items() if b == "output_image"), None)
        if out is None:
            return unknown("tidak ada baris harga output_image")
        inp = next((p for (b, _), p in rows.items() if b == "input_image"), None)
        unit, price = out["unit"], float(out["cost_usd"])
        if unit == "image":
            lo = hi = price * n_outputs
            conf = "exact"
        elif unit == "megapixel":
            lo_mp, hi_mp = (MEGAPIXELS[resolution],) * 2 if resolution in MEGAPIXELS else (1.0, 4.0)
            lo, hi = price * lo_mp * n_outputs, price * hi_mp * n_outputs
            conf = "formula"
        elif unit == "token":
            if history:
                lo, hi = min(history) * n_outputs, max(history) * HISTORY_MARGIN * n_outputs
                conf = "history"
            else:
                lo, hi = 0.0, price * IMAGE_OUTPUT_TOKENS_CEILING * n_outputs
                conf = "bound"
            inp = None if history else inp   # biaya input sudah ada dalam riwayat
        else:
            return unknown(f"satuan harga tidak dikenal: {unit}")
        if inp and n_inputs:
            iu, ip = inp["unit"], float(inp["cost_usd"])
            add = ip * n_inputs * (IMAGE_INPUT_TOKENS_PER_IMAGE if iu == "token" else 1)
            hi += add
            if iu == "token":
                conf = "bound" if conf == "exact" else conf
        lows.append(lo); highs.append(hi); confidences.append(conf)
        basis.append(f"{ep.get('provider_name', '?')}: {unit} ${price}")
    order = ["exact", "formula", "history", "bound"]
    confidence = max(confidences, key=order.index)
    return Estimate(min(lows), max(highs), confidence, basis)


# ---------- kartu harga untuk katalog model (plan 05, revisi 2) ----------
# Semua angka berasal dari estimate_video/estimate_image di atas, jadi kartu dan /api/estimate tidak bisa berbeda rumus.

def _est(e: Estimate) -> dict:
    return {"low": round(e.low, 6), "high": round(e.high, 6), "confidence": e.confidence}


def video_category(info: dict) -> str:
    mid = (info.get("id") or "").lower()
    if "first_frame" in (info.get("supported_frame_images") or []):
        return "i2v"
    if "upscale" in mid:
        return "upscale"
    if "avatar" in mid:
        return "avatar"
    if "edit" in mid or "aleph" in mid:
        return "edit"
    return "other"


_VIDEO_DISABLED = {
    "upscale": "Upscale video: butuh video sumber, bukan gambar awal",
    "avatar": "Avatar bicara: butuh foto + audio, bukan alur gambar ke video",
    "edit": "Edit video: butuh video sumber (dipakai di Tiru Gerakan)",
    "other": "Tidak mendukung gambar sebagai frame awal",
}


def video_price_card(info: dict) -> dict:
    """Harga per detik per resolusi (tanpa minimum per generasi) + contoh 5 detik resolusi terendah."""
    skus = info.get("pricing_skus") or {}
    no_min = {**info, "pricing_skus": {k: v for k, v in skus.items() if k != "minimum_cents_per_generation"}}
    resolutions = info.get("supported_resolutions") or [None]
    audio_opts = [False] if info.get("generate_audio") is False else [False, True]
    rows = []
    for res in resolutions:
        per_audio = {}
        for audio in audio_opts:
            e = estimate_video(no_min, duration=1, resolution=res, audio=audio, image_inputs=0)
            per_audio[audio] = e
        same = len(per_audio) == 1 or per_audio[False].high == per_audio[True].high
        for audio, e in ([(None, per_audio[False])] if same else list(per_audio.items())):
            rows.append({"label": res or "semua resolusi", "audio": audio, "usd_per_second": None if e.confidence == "unknown" else round(e.high, 6),
                         "confidence": e.confidence, "basis": e.basis[:1]})
    durations = info.get("supported_durations") or []
    dur = 5 if (not durations or 5 in durations) else min(durations)
    ranked = sorted([r for r in resolutions if r in SHORT_SIDE], key=SHORT_SIDE.get)
    res = ranked[0] if ranked else resolutions[0]
    example = {"label": f"{dur} detik" + (f" · {res}" if res else ""), **_est(estimate_video(
        info, duration=dur, resolution=res, audio=False, image_inputs=1))}
    notes = []
    if (m := _usd(skus, "minimum_cents_per_generation")):
        notes.append(f"minimum ${m:.2f} per generasi")
    if (i := _usd(skus, "cents_per_image_input")):
        notes.append(f"${i:.2f} per gambar input")
    cat = video_category(info)
    return {"category": cat, "rows": rows, "example": example, "notes": notes,
            "selectable": cat == "i2v", "disabled_reason": None if cat == "i2v" else _VIDEO_DISABLED[cat]}


def image_price_card(info: dict, endpoints: list[dict] | None, error: str | None = None,
                     history: list[float] | None = None) -> dict:
    """Harga per satuan apa adanya per provider + contoh 1 gambar dengan 1 gambar input."""
    can_edit = "image" in ((info.get("architecture") or {}).get("input_modalities") or [])
    rows, example, notes = [], {"label": "1 gambar", "low": 0.0, "high": 0.0, "confidence": "unknown"}, []
    if endpoints:
        for ep in endpoints:
            for p in ep.get("pricing", []):
                rows.append({"provider": ep.get("provider_name", "?"), "billable": p.get("billable"),
                             "unit": p.get("unit"), "usd": p.get("cost_usd"), "variant": p.get("variant")})
        example = {"label": "1 gambar" + (" + 1 input" if can_edit else ""),
                   **_est(estimate_image(endpoints, n_inputs=1 if can_edit else 0, history=history))}
        if example["confidence"] == "unknown":
            notes.append("satuan harga tidak dikenal estimator")
    else:
        notes.append(error or "harga tidak tersedia")
    return {"category": "image_edit" if can_edit else "text_to_image", "rows": rows, "example": example, "notes": notes,
            "selectable": can_edit,
            "disabled_reason": None if can_edit else "Hanya teks ke gambar: tidak menerima gambar sumber untuk diedit"}
