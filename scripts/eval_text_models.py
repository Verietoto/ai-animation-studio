"""Eval model teks (plan 17): kepatuhan JSON dan kualitas keluaran pada kasus tetap, dengan model nyata. Biaya dibatasi keras.

Jalankan dari backend/:
  set -a; . ../.env; set +a; PYTHONPATH=. ../.venv/bin/python ../scripts/eval_text_models.py OUT.json [--cap 0.30] [--max-call 0.10] [model ...]
Kunci API hanya dibaca dari lingkungan dan tidak dicetak. Tiap panggilan dihitung estimasinya dulu; dilewati bila melewati sisa batas.
"""
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from app import blockout, script, textai
from app.config import Settings
from app.openrouter import OpenRouterClient

DEFAULT_MODELS = ["anthropic/claude-haiku-5.5", "openai/gpt-oss-120b", "deepseek/deepseek-v4.1-flash", "qwen/qwen3.7-flash",
                  "google/gemma-3-12b-it", "openai/gpt-5-nano"]
CHARS = [{"id": "c_rani", "name": "Rani", "description": "gadis desa 17 tahun, rambut dikepang, riang"},
         {"id": "c_budi", "name": "Budi", "description": "penjaga warung kopi, 40 tahun, pendiam dan baik hati"},
         {"id": "c_momon", "name": "Momon", "description": "kucing oranye gemuk milik Rani, suka tidur"}]
LOCS = [{"id": "l_warung", "name": "Warung kopi", "description": "warung kayu kecil dengan lampu temaram"},
        {"id": "l_sawah", "name": "Sawah", "description": "hamparan sawah saat senja"}]
SCRIPT_TEXT = ("#[Sawah] senja. @[Rani] berjalan pulang sambil membawa keranjang, @[Momon] mengikuti di belakangnya. "
               "Mereka tiba di #[Warung kopi]. @[Budi] mengelap gelas dan menyapa: Budi: Kamu pulang juga. "
               "@[Rani] tersenyum dan duduk; @[Momon] melompat ke meja dan menggulung badan.")
BLOCKOUT_CTX = [
    {"duration": 5, "ratio": "16:9", "location": LOCS[1], "time_of_day": "senja", "camera": "wide shot, perlahan dolly in", "dialogue": "",
     "extra": "", "cast": [{"character_id": "c_rani", "name": "Rani", "action": "berjalan membawa keranjang"},
                            {"character_id": "c_momon", "name": "Momon", "action": "mengikuti di belakang"}]},
    {"duration": 4, "ratio": "16:9", "location": LOCS[0], "time_of_day": "malam", "camera": "medium shot dari sisi meja", "dialogue": "Budi: Kamu pulang juga.",
     "extra": "", "cast": [{"character_id": "c_budi", "name": "Budi", "action": "mengelap gelas lalu menyapa"},
                            {"character_id": "c_momon", "name": "Momon", "action": "melompat ke meja"}]},
]


def _blockout_case(ctx):
    cast_ids = [c["character_id"] for c in ctx["cast"]]

    def check(raw):
        raw["actors"] = [a for a in raw.get("actors") or [] if isinstance(a, dict) and a.get("character_id") in cast_ids]
        raw["duration"] = ctx["duration"]
        layout = blockout.clean(raw, cast_ids)   # melempar ServiceError bila tidak valid
        return [] if len(layout["actors"]) == len(cast_ids) else ["tidak semua tokoh diberi aktor"]
    return ("blockout", blockout.SYSTEM, blockout.user_prompt(ctx), 6000, check)


def _split_check(raw):
    scenes, warnings = script.clean_split(raw.get("scenes"), [c["id"] for c in CHARS], [l["id"] for l in LOCS])
    return ([] if len(scenes) >= 3 else ["kurang dari 3 adegan"]) + warnings[:3]


def _script_check(raw):
    text = raw.get("script") or ""
    unknown = script.analyze(text, CHARS, LOCS)["unknown"]
    return (["naskah terlalu pendek"] if len(text) < 600 else []) + [f"mention tak dikenal: {u['name']}" for u in unknown[:3]]


CASES = [_blockout_case(BLOCKOUT_CTX[0]), _blockout_case(BLOCKOUT_CTX[1]),
         ("split", script.SPLIT_SYSTEM, script.split_user(SCRIPT_TEXT, CHARS, LOCS, "16:9"), 12000, _split_check),
         ("script", script.SCRIPT_SYSTEM, script.script_user("Pulang ke Desa", "Rani pulang ke desa bersama kucingnya, Momon, lalu bertemu Budi di warung kopi.", CHARS, LOCS, ""), 4000, _script_check)]


def main(argv: list[str]) -> None:
    cap, max_call = 0.30, 0.10
    models, out_path, i = [], Path(argv[0]), 1
    while i < len(argv):
        if argv[i] == "--cap":
            cap = float(argv[i + 1]); i += 2
        elif argv[i] == "--max-call":
            max_call = float(argv[i + 1]); i += 2
        else:
            models.append(argv[i]); i += 1
    models = models or DEFAULT_MODELS
    cfg = Settings.from_env()
    st = SimpleNamespace(client=OpenRouterClient(cfg.api_key, cfg.base_url), s=cfg, _text_catalog=None)
    spent, results = 0.0, []
    for mid in models:
        try:
            meta = textai.info(st, mid)
        except Exception as exc:
            print(f"{mid}: dilewati ({exc})"); continue
        for name, system, user, max_tokens, check in CASES:
            est = textai.estimate(st, system, user, max_tokens, model=mid)
            if est.high > max_call or spent + est.high > cap:
                print(f"{mid} {name}: dilewati (estimasi ${est.high:.3f})"); results.append({"model": mid, "case": name, "skipped": True}); continue
            t0 = time.time()
            row = {"model": mid, "case": name, "structured": meta["structured"], "reasoning": meta["reasoning"]}
            try:
                resp = textai._call(st, meta, system, user, max_tokens, None)
                row["cost"] = (resp.get("usage") or {}).get("cost") or 0.0
                spent += row["cost"]
                choice = resp["choices"][0]
                content = ((choice.get("message") or {}).get("content") or "").strip()
                row["finish"] = choice.get("finish_reason")
                try:
                    json.loads(content); row["json_clean"] = True
                except ValueError:
                    row["json_clean"] = False
                try:
                    raw = textai.parse_json(content); row["json_usable"] = True
                    try:
                        row["problems"] = check(raw); row["ok"] = not row["problems"]
                    except Exception as exc:
                        row["problems"] = [f"{type(exc).__name__}: {str(exc)[:120]}"]; row["ok"] = False
                except ValueError:
                    row["json_usable"] = False; row["ok"] = False; row["problems"] = ["JSON tidak terbaca" if content else "jawaban kosong"]
            except Exception as exc:
                row.update({"error": str(exc)[:160], "ok": False, "json_clean": False, "json_usable": False, "cost": 0.0})
            row["seconds"] = round(time.time() - t0, 1)
            results.append(row)
            print(f"{mid} {name}: {'OK ' if row['ok'] else 'GAGAL'} clean={row['json_clean']} ${row.get('cost', 0):.4f} {row['seconds']}s "
                  f"{(row.get('problems') or [row.get('error')])[:2] if not row['ok'] else ''}")
    out_path.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(f"total ${spent:.4f} dari batas ${cap:.2f}")


if __name__ == "__main__":
    main(sys.argv[1:])
