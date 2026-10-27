"""Spike plan 16: kualitas potret karakter dari deskripsi (teks ke gambar), model nyata. Tepat 4 panggilan; biaya terburuk < $0.15.

Jalankan dari backend/:  set -a; . ../.env; set +a; PYTHONPATH=. ../.venv/bin/python ../scripts/spike_portrait.py OUT_DIR
Kunci API hanya dibaca dari lingkungan dan tidak dicetak.
"""
import base64
import sys
from pathlib import Path

from app import sceneprompt
from app.config import Settings
from app.openrouter import OpenRouterClient

MODEL = "bytedance-seed/seedream-5-0-flash"
HARD_CAP_USD = 0.15
DESCRIPTIONS = {
    "anime_gadis": "Gadis desa 17 tahun, rambut hitam dikepang dua, kebaya merah dengan kain batik, sandal jerami, gaya anime berwarna cerah",
    "kartun_lelaki": "Pria 40 tahun penjaga warung kopi, perut agak buncit, kumis tipis, kaus putih dan celemek cokelat, gaya kartun 2D sederhana",
    "nenek_3d": "Nenek 70 tahun berambut putih disanggul, kebaya hijau tua dan sarung, kacamata bulat, gaya animasi 3D ramah anak",
    "realistis": "Wanita Indonesia 28 tahun, rambut bob hitam, jaket denim biru, kaus putih, celana hitam, gaya foto-realistik",
}


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    cfg = Settings.from_env()
    client = OpenRouterClient(cfg.api_key, cfg.base_url)
    total = 0.0
    for name, desc in DESCRIPTIONS.items():
        if total >= HARD_CAP_USD:
            print("batas biaya tercapai, berhenti")
            break
        try:
            resp = client.generate_image(MODEL, sceneprompt.portrait_prompt(desc), aspect_ratio="3:4")
        except Exception as exc:   # spike: laporkan apa adanya
            print(f"{name}: GAGAL {str(exc)[:160]}")
            continue
        cost = (resp.get("usage") or {}).get("cost") or 0.0
        total += cost
        data = (resp.get("data") or [{}])[0].get("b64_json")
        if data:
            (out / f"{name}.png").write_bytes(base64.b64decode(data))
        print(f"{name}: ${cost:.4f} {'tersimpan' if data else 'TANPA GAMBAR'}")
    print(f"total ${total:.4f}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
