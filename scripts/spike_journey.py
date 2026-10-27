"""Spike plan 15 fase B: AI menulis naskah lalu memecahnya jadi adegan, model nyata. Tepat 2 panggilan chat; biaya terburuk < $0.03.

Jalankan dari backend/:  set -a; . ../.env; set +a; PYTHONPATH=. ../.venv/bin/python ../scripts/spike_journey.py OUT_DIR
Kunci API hanya dibaca dari lingkungan dan tidak dicetak.
"""
import json
import sys
from pathlib import Path

from app import script
from app.config import Settings
from app.openrouter import OpenRouterClient

CHARS = [{"id": "c_rani", "name": "Rani", "description": "gadis desa 17 tahun, rambut dikepang, riang"},
         {"id": "c_budi", "name": "Budi", "description": "penjaga warung kopi, 40 tahun, pendiam dan baik hati"},
         {"id": "c_siti", "name": "Siti", "description": "nenek Rani, bijak, bersarung"}]
LOCS = [{"id": "l_warung", "name": "Warung kopi", "description": "warung kayu kecil dengan lampu temaram"},
        {"id": "l_sawah", "name": "Sawah", "description": "hamparan sawah saat senja"},
        {"id": "l_rumah", "name": "Rumah Nenek", "description": "rumah panggung sederhana"}]


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    cfg = Settings.from_env()
    client = OpenRouterClient(cfg.api_key, cfg.base_url)
    total = 0.0

    def ask(system: str, user: str, max_tokens: int, name: str) -> dict:
        nonlocal total
        resp = client.chat_json(cfg.blockout_model, system, user, max_tokens)
        cost = (resp.get("usage") or {}).get("cost") or 0.0
        total += cost
        text = resp["choices"][0]["message"]["content"].strip()
        (out / f"{name}_raw.txt").write_text(text)
        print(f"{name}: ${cost:.5f}, {len(text)} karakter")
        return json.loads(text.strip("`").removeprefix("json").strip())

    draft = ask(script.SCRIPT_SYSTEM, script.script_user("Pulang ke Desa", "Rani pulang ke desa setelah setahun merantau, bertemu Budi di warung kopi lalu menemui neneknya di rumah.", CHARS, LOCS, ""), 4000, "script")
    text = draft["script"]
    (out / "script.txt").write_text(text)
    unknown = script.analyze(text, CHARS, LOCS)
    print(f"naskah {len(text)} karakter | mention: {len(script.mentions(text))} | tak dikenal: {unknown['unknown']}")
    split = ask(script.SPLIT_SYSTEM, script.split_user(text, CHARS, LOCS, "16:9"), 12000, "split")
    scenes, warnings = script.clean_split(split.get("scenes"), [c["id"] for c in CHARS], [l["id"] for l in LOCS])
    (out / "scenes.json").write_text(json.dumps(scenes, indent=1, ensure_ascii=False))
    print(f"adegan {len(scenes)} | total detik {sum(s['planned_seconds'] for s in scenes)} | peringatan {len(warnings)}: {warnings[:4]}")
    for n, s in enumerate(scenes[:4], 1):
        print(f" {n}. loc={s['location_id']} {s['planned_seconds']}s cast={[(c['character_id'], c['action'][:40]) for c in s['cast']]} cam={s['camera'][:40]!r}")
    print(f"total ${total:.5f}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
