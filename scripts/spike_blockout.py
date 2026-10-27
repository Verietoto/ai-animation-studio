"""Spike plan 14: AI penyusun blockout dengan model nyata. Maks 2 panggilan chat (max_tokens 6000), biaya terburuk < $0.01.

Jalankan dari backend/:  set -a; . ../.env; set +a; ../.venv/bin/python ../scripts/spike_blockout.py OUT_DIR
Kunci API hanya dibaca dari lingkungan dan tidak dicetak.
"""
import json
import sys
from pathlib import Path

from app import blockout
from app.config import Settings
from app.openrouter import OpenRouterClient

HARD_CAP_USD = 0.02
SCENES = [
    {"duration": 5, "ratio": "16:9", "location": {"name": "Warung kopi", "description": "warung kayu kecil, meja panjang, lampu temaram"},
     "time_of_day": "senja", "camera": "medium shot dari sisi meja, perlahan dolly in", "dialogue": "Rani: Kamu datang juga.",
     "extra": "", "cast": [{"character_id": "c_rani", "name": "Rani", "action": "duduk di meja lalu menoleh ke pintu dan melambai"},
                            {"character_id": "c_budi", "name": "Budi", "action": "berjalan masuk dari pintu menuju meja"}]},
    {"duration": 4, "ratio": "9:16", "location": {"name": "Jalan desa", "description": "jalan tanah di antara sawah"},
     "time_of_day": "pagi", "camera": "wide shot rendah, mengikuti dari belakang", "dialogue": "", "extra": "",
     "cast": [{"character_id": "c_rani", "name": "Rani", "action": "berlari menyusuri jalan menjauhi kamera"}]},
]


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    cfg = Settings.from_env()
    client = OpenRouterClient(cfg.api_key, cfg.base_url)
    total = 0.0
    for n, ctx in enumerate(SCENES, 1):
        if total >= HARD_CAP_USD:
            print("batas biaya tercapai, berhenti")
            break
        resp = client.chat_json(cfg.blockout_model, blockout.SYSTEM, blockout.user_prompt(ctx), 6000)
        cost = (resp.get("usage") or {}).get("cost") or 0.0
        total += cost
        text = resp["choices"][0]["message"]["content"].strip()
        (out / f"scene{n}_raw.txt").write_text(text)
        try:
            raw = json.loads(text.strip("`").removeprefix("json").strip())
            ids = [c["character_id"] for c in ctx["cast"]]
            raw["actors"] = [a for a in raw.get("actors", []) if a.get("character_id") in ids]
            raw["duration"] = ctx["duration"]
            layout = blockout.clean(raw, ids)
            (out / f"scene{n}_layout.json").write_text(json.dumps(layout, indent=1))
            print(f"adegan {n}: OK ${cost:.5f} | kamera {len(layout['camera']['keys'])} key | "
                  f"aktor {[(a['character_id'], [k['pose'] for k in a['keys']]) for a in layout['actors']]} | props {len(layout['props'])}")
        except Exception as exc:   # spike: laporkan apa adanya
            print(f"adegan {n}: GAGAL ${cost:.5f} {type(exc).__name__}: {exc}")
    print(f"total ${total:.5f}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
