"""Kosakata blockout bersama Python dan TypeScript (plan 17): `shared/blockout_vocabulary.json` adalah satu-satunya sumber.

Berisi bentuk, objek siap pakai (ukuran, permukaan atas), jenis tubuh (sendi, batas sudut, pose, siklus gerak), preset waktu/cuaca,
dan konstanta lensa. Frontend mengimpor berkas yang sama saat build, jadi tabel tidak bisa menyimpang.
"""
import json
import math
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "shared" / "blockout_vocabulary.json"


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads(PATH.read_text())


def shapes() -> list[str]:
    return load()["shapes"]


def prefabs() -> dict[str, dict]:
    return load()["prefabs"]


def bodies() -> dict[str, dict]:
    return load()["bodies"]


def prop_types() -> list[str]:
    return [*shapes(), *prefabs()]


def fov_for(mm: float, aspect: float) -> float:
    """Lensa (mm, sensor sisi pendek `sensor_short_mm`) -> FOV vertikal derajat; HARUS sama dengan fovFor di blockoutMath.ts."""
    short = 2 * math.atan(load()["lens"]["sensor_short_mm"] / 2 / mm)
    return math.degrees(short if aspect >= 1 else 2 * math.atan(math.tan(short / 2) / aspect))
