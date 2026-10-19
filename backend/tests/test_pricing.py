import json
from pathlib import Path

import pytest

from app import pricing

FIX = Path(__file__).parent / "fixtures"
MODELS = {m["id"]: m for m in json.loads((FIX / "video_models.json").read_text())["data"]}


def v(model, **kw):
    kw.setdefault("audio", False)
    return pricing.estimate_video(MODELS[model], **kw)


def approx(a, b):
    return a == pytest.approx(b, rel=1e-6)


def test_grok_lite_matches_real_billing():
    # kalibrasi nyata (2026-10-19): 1 detik 480p + 1 gambar input = $0,03 diperkirakan, $0,03 nyata
    e = v("x-ai/grok-imagine-video-1.5-lite", duration=1, resolution="480p", image_inputs=1)
    assert e.confidence == "exact" and approx(e.low, 0.03) and approx(e.high, 0.03)


@pytest.mark.parametrize("model,res,audio,dur,expected", [
    ("alibaba/wan-3.0", "480p", False, 2, 0.10),
    ("alibaba/wan-3.0", "1080p", True, 10, 2.00),
    ("kwaivgi/kling-v3.0-pro", "720p", False, 5, 0.56),
    ("kwaivgi/kling-v3.0-pro", "720p", True, 5, 0.84),
    ("google/veo-3.1", "1080p", True, 8, 3.20),       # SKU tanpa akhiran = tier default
    ("google/veo-3.1", "4K", False, 8, 3.20),
    ("google/veo-3.1-fast", "720p", False, 4, 0.32),
    ("google/veo-3.1-lite", "720p", True, 8, 0.40),
    ("black-forest-labs/flux-3-video", "1080p", True, 5, 1.45),
    ("runway/gen-4.5", "720p", False, 5, 0.60),
    ("minimax/hailuo-3", "2K", True, 5, 0.65),
    ("alibaba/wan-2.6", "480p", False, 5, 0.20),       # tidak ada SKU i2v 480p -> t2v 480p
    ("alibaba/wan-2.6", "720p", False, 5, 0.50),       # i2v 720p
    ("x-ai/grok-imagine-video-1.5", "1080p", False, 10, 2.50),
])
def test_per_second_models_hand_computed(model, res, audio, dur, expected):
    e = v(model, duration=dur, resolution=res, audio=audio)
    assert e.confidence == "exact", e
    assert approx(e.low, expected) and approx(e.high, expected)


def test_seedance_token_formula_matches_published_per_second_prices():
    # review resmi Seedance 2.5: sekitar $0,103/dtk di 480p dan $0,231/dtk di 720p
    e480 = v("bytedance/seedance-2.5", duration=10, resolution="480p", audio=True)
    e720 = v("bytedance/seedance-2.5", duration=10, resolution="720p", audio=True)
    assert e480.confidence == "formula"
    assert 1.00 < e480.low / 1.10 < 1.06 and 2.25 < e720.low / 1.10 < 2.37
    assert e480.high >= e480.low


def test_seedance_without_audio_cheaper_only_for_1_5_pro():
    a = v("bytedance/seedance-1-5-pro", duration=4, resolution="720p", audio=True)
    b = v("bytedance/seedance-1-5-pro", duration=4, resolution="720p", audio=False)
    assert b.low == pytest.approx(a.low / 2)


def test_seedance_video_input_uses_cheaper_rate_but_adds_input_tokens():
    plain = v("bytedance/seedance-2.5", duration=5, resolution="480p", audio=True)
    ref = v("bytedance/seedance-2.5", duration=5, resolution="480p", audio=True, video_input_seconds=5)
    assert ref.low > plain.low            # token video input ikut dihitung (konservatif)


def test_minimum_per_generation_applies():
    e = v("runway/aleph-2", duration=None, resolution=None, mode="edit", video_input_seconds=1)
    assert approx(e.low, 0.56) and any("minimum" in b for b in e.basis)
    e = v("runway/aleph-2", duration=None, resolution=None, mode="edit", video_input_seconds=10)
    assert approx(e.low, 2.80)


def test_flux_video_edit_per_second_of_source():
    e = v("black-forest-labs/flux-video-edit", duration=None, resolution=None, mode="edit", video_input_seconds=5)
    assert approx(e.low, 0.15)


def test_reference_images_add_cost():
    e = v("minimax/hailuo-3", duration=5, resolution="2K", audio=True, reference_images=2)
    assert approx(e.low, 0.65 + 0.08)


def test_unspecified_resolution_gives_conservative_range():
    e = v("x-ai/grok-imagine-video-1.5-lite", duration=10, resolution=None)
    assert approx(e.low, 0.20) and approx(e.high, 1.40) and e.low < e.high


def test_unspecified_duration_uses_supported_range():
    e = v("alibaba/wan-3.0", duration=None, resolution="480p")
    assert approx(e.low, 0.10) and approx(e.high, 1.50)


def test_unsupported_pricing_unit_is_unknown_not_guessed():
    e = v("black-forest-labs/flux-video-upscale", duration=5, resolution=None)
    assert e.confidence == "unknown"


def test_unknown_when_no_skus_or_no_matching_resolution():
    assert pricing.estimate_video({"pricing_skus": {}}, duration=5, resolution="720p", audio=False).confidence == "unknown"
    info = {"pricing_skus": {"video_tokens": "0.00001"}, "supported_resolutions": ["8K"]}
    assert pricing.estimate_video(info, duration=5, resolution="8K", audio=False).confidence == "unknown"


def test_every_real_model_is_estimated_or_explicitly_unknown():
    """Tidak ada model yang melempar error; hanya upscale (megapiksel-detik) yang boleh unknown."""
    unknowns = []
    for model_id, info in MODELS.items():
        dur = (info.get("supported_durations") or [5])[0]
        e = pricing.estimate_video(info, duration=dur, resolution=None, audio=False,
                                   mode="edit" if not info.get("supported_frame_images") else "i2v",
                                   video_input_seconds=5)
        if e.confidence == "unknown":
            unknowns.append(model_id)
        else:
            assert e.high >= e.low >= 0, model_id
    assert unknowns == ["black-forest-labs/flux-video-upscale"] or set(unknowns) <= {
        "black-forest-labs/flux-video-upscale", "heygen/avatar-iv"}, unknowns


def eps(name):
    return json.loads((FIX / f"{name}_endpoints.json").read_text())["endpoints"]


def test_image_per_image_pricing_is_exact():
    e = pricing.estimate_image(eps("seedream"), n_outputs=2)
    assert e.confidence == "exact" and approx(e.low, 0.08) and approx(e.high, 0.08)


def test_image_token_pricing_without_history_is_bound():
    e = pricing.estimate_image(eps("gpt_image_2"), n_inputs=1)
    assert e.confidence == "bound" and e.low == 0
    assert approx(e.high, 3e-05 * pricing.IMAGE_OUTPUT_TOKENS_CEILING + 8e-06 * pricing.IMAGE_INPUT_TOKENS_PER_IMAGE)
    assert e.high > 0.0151       # di atas biaya nyata terukur


def test_image_token_pricing_uses_history_when_available():
    e = pricing.estimate_image(eps("gpt_image_2"), n_inputs=1, history=[0.0119, 0.0151])
    assert e.confidence == "history" and approx(e.low, 0.0119) and approx(e.high, 0.0151 * 1.5)


def test_image_estimate_takes_worst_provider():
    e = pricing.estimate_image(eps("gemini_image"), n_inputs=0)
    assert approx(e.high, 0.00012 * pricing.IMAGE_OUTPUT_TOKENS_CEILING)


def test_image_without_pricing_is_unknown():
    assert pricing.estimate_image([]).confidence == "unknown"
    assert pricing.estimate_image([{"pricing": [{"billable": "output_image", "unit": "weird", "cost_usd": 1}]}]).confidence == "unknown"
