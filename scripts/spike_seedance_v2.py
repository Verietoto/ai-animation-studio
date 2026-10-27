"""Spike plan 18 (fase 0): kemampuan Seedance 2.x lewat OpenRouter untuk Storyboard v2. Tanpa plafon biaya (keputusan user,
plan 18 Revisi 2); biaya tiap uji dicetak dan ditulis ke OUT_DIR/summary.json.

Jalankan dari backend/:  set -a; . ../.env; set +a; PYTHONPATH=. ../.venv/bin/python ../scripts/spike_seedance_v2.py OUT_DIR
Kunci API hanya dibaca dari lingkungan dan tidak dicetak. Butuh cloudflared (URL publik untuk audio/video) dan `say` + ffmpeg.
"""
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

from app import media
from app.config import Settings
from app.openrouter import OpenRouterClient, OpenRouterError
from app.publicmedia import TunnelPublicMedia

IMG_MODEL = "bytedance-seed/seedream-5-0-flash"
MINI = "bytedance/seedance-2.0-mini"
FULL = "bytedance/seedance-2.0"
ASSETS = {
    "momon": "Kucing oranye kartun bernama Momon, berdiri dua kaki, mata besar bulat, syal biru, gaya kartun 2D berwarna cerah, latar putih polos, seluruh badan",
    "sari": "Gadis kartun bernama Sari, rambut hitam dikepang dua, kebaya merah, gaya kartun 2D berwarna cerah, latar putih polos, seluruh badan",
    "ruang": "Ruang tamu hangat bergaya kartun 2D, sofa hijau, jendela besar, tanaman, tanpa tokoh, cahaya sore",
}
BEATS = {   # tiga bingkai acuan per detik; konsistensi dengan sheet diamati manual
    "beat1": "Kartun 2D: kucing oranye bersyal biru (Momon) berdiri di pintu ruang tamu hangat, sofa hijau di belakang, shot medium",
    "beat2": "Kartun 2D: kucing oranye bersyal biru (Momon) melompat ke sofa hijau, ruang tamu hangat, shot lebar",
    "beat3": "Kartun 2D: close-up kucing oranye bersyal biru (Momon) di atas sofa hijau, mulut terbuka berbicara, wajah besar di bingkai",
}
costs: dict[str, float | None] = {}
notes: dict[str, str] = {}


def img_ref(path: Path) -> dict:
    return {"type": "image_url", "image_url": {"url": media.to_data_url(path.read_bytes())}}


def gen_image(client, name: str, prompt: str, out: Path, ratio: str = "16:9", refs: list[Path] | None = None) -> Path:
    dst = out / f"{name}.png"
    if dst.exists():
        return dst
    if refs:
        try:
            resp = client.edit_image(IMG_MODEL, prompt, [media.to_data_url(p.read_bytes()) for p in refs], aspect_ratio=ratio)
        except OpenRouterError as exc:
            print(f"  {name}: edit gagal ({str(exc)[:80]}), pakai teks saja")
            resp = client.generate_image(IMG_MODEL, prompt, aspect_ratio=ratio)
    else:
        resp = client.generate_image(IMG_MODEL, prompt, aspect_ratio=ratio)
    cost = (resp.get("usage") or {}).get("cost") or 0.0
    costs[f"img:{name}"] = cost
    dst.write_bytes(base64.b64decode(resp["data"][0]["b64_json"]))
    print(f"  gambar {name}: ${cost:.4f}")
    return dst


def run_job(client, name: str, payload: dict, out: Path, wait: int = 900) -> dict:
    """Kirim satu job, tunggu selesai, simpan MP4, kembalikan ringkasan (status, biaya, error)."""
    try:
        resp = client.submit_video(payload)
    except OpenRouterError as exc:
        print(f"[{name}] DITOLAK: {str(exc)[:300]}")
        notes[name] = f"ditolak: {str(exc)[:300]}"
        return {"name": name, "status": "rejected", "error": str(exc)[:300]}
    jid = resp.get("id")
    t0 = time.time()
    job: dict = {}
    while time.time() - t0 < wait:
        time.sleep(8)
        job = client.get_video_job(jid)
        if str(job.get("status", "")).lower() in ("completed", "failed", "cancelled", "expired"):
            break
    status = str(job.get("status", "")).lower()
    cost = (job.get("usage") or {}).get("cost")
    costs[f"vid:{name}"] = cost
    row = {"name": name, "id": jid, "status": status, "cost": cost, "error": job.get("error"), "urls": job.get("urls")}
    if status == "completed":
        data = client.download_video(jid)
        (out / f"{name}.mp4").write_bytes(data)
        info = media.probe(out / f"{name}.mp4")
        row["duration"], row["size"], row["has_audio"] = info["duration"], f'{info["width"]}x{info["height"]}', info["has_audio"]
    print(f"[{name}] {status} ${cost} {row.get('duration')}s {row.get('size')} audio={row.get('has_audio')} {row.get('error') or ''}")
    return row


def make_voice(out: Path, name: str, text: str, voice: str) -> Path:
    aiff = out / f"{name}.aiff"
    subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True)
    m4a = out / f"{name}.m4a"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(aiff), "-ac", "1", "-ar", "48000", "-c:a", "aac", str(m4a)], check=True)
    return m4a


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    cfg = Settings.from_env()
    client = OpenRouterClient(cfg.api_key, cfg.base_url)
    results: list[dict] = []

    print("== aset ==")
    img = {k: gen_image(client, k, v, out, "3:4" if k != "ruang" else "16:9") for k, v in ASSETS.items()}
    beats = {k: gen_image(client, k, v, out, "16:9", refs=[img["momon"], img["ruang"]]) for k, v in BEATS.items()}

    print("== 6. katalog TTS/audio (gratis) ==")
    try:
        models = client.list_models()
        audio_out = [m["id"] for m in models if "audio" in ((m.get("architecture") or {}).get("output_modalities") or [])]
        speech = [m["id"] for m in models if any(w in m["id"].lower() for w in ("tts", "speech", "voice"))]
        notes["tts_models"] = json.dumps({"output_audio": audio_out, "nama_mirip_tts": speech})
        print("  output audio:", audio_out[:10], "| nama tts:", speech[:10])
    except Exception as exc:
        notes["tts_models"] = f"gagal: {exc}"

    print("== jalur publik (cloudflared) untuk audio/video ==")
    pub = TunnelPublicMedia(ttl=7200)
    voice = make_voice(out, "suara_momon_en", "I am so hungry. Where is my dinner?", "Samantha")
    key_a, url_a = pub.publish(voice)
    print("  audio terbit (URL tidak dicetak penuh):", url_a[:30] + "...")

    base = {"model": MINI, "resolution": "480p", "aspect_ratio": "16:9", "generate_audio": True}
    pg = [
        # 1. penomoran referensi: @Image N vs "image N"
        ("t1a_at", {**base, "duration": 5, "input_references": [img_ref(img["momon"]), img_ref(img["sari"]), img_ref(img["ruang"])],
                    "prompt": "@Image 1 is Momon the orange cat. @Image 2 is Sari the girl. @Image 3 is the living room. Momon and Sari sit on the sofa in @Image 3 and wave at the camera."}),
        ("t1b_plain", {**base, "duration": 5, "input_references": [img_ref(img["momon"]), img_ref(img["sari"]), img_ref(img["ruang"])],
                       "prompt": "Image 1 is Momon the orange cat. Image 2 is Sari the girl. Image 3 is the living room. Momon and Sari sit on the sofa in the living room of image 3 and wave at the camera."}),
        # 2. prompt bertimecode + gambar beat
        ("t2_timecode", {**base, "duration": 9, "input_references": [img_ref(beats["beat1"]), img_ref(beats["beat2"]), img_ref(beats["beat3"])],
                         "prompt": ("@Image 1, @Image 2, @Image 3 are the keyframes of shots 1, 2, 3. "
                                    "[0-3s] Shot 1 like @Image 1: Momon stands at the door. "
                                    "[3-6s] Shot 2 like @Image 2: Momon jumps onto the sofa. "
                                    "[6-9s] Shot 3 like @Image 3: close-up of Momon who says \"I am so hungry!\".")}),
        # 4. sembilan gambar
        ("t4_nine", {**base, "duration": 4, "input_references": [img_ref(p) for p in [*beats.values(), img["momon"], img["sari"], img["ruang"], *beats.values()]][:9],
                     "prompt": "Use all nine references: Momon the orange cat walks through the living room. Cartoon style."}),
        # 8. dialog bahasa Indonesia vs Inggris
        ("t8_dialog_id", {**base, "duration": 6, "input_references": [img_ref(img["momon"]), img_ref(img["ruang"])],
                          "prompt": "Momon the orange cat (@Image 1) in the living room (@Image 2) looks at the camera and says in Indonesian: \"Aku lapar sekali, mana makan malamku?\""}),
        ("t8_dialog_en", {**base, "duration": 6, "input_references": [img_ref(img["momon"]), img_ref(img["ruang"])],
                          "prompt": "Momon the orange cat (@Image 1) in the living room (@Image 2) looks at the camera and says: \"I am so hungry, where is my dinner?\""}),
        # kalibrasi biaya: 720p dengan audio pada model penuh; mini tanpa audio
        ("c1_full_720_audio", {"model": FULL, "resolution": "720p", "aspect_ratio": "16:9", "generate_audio": True, "duration": 4,
                               "input_references": [img_ref(img["momon"]), img_ref(img["ruang"])], "prompt": "Momon the orange cat walks across the living room."}),
        ("c2_mini_480_noaudio", {**base, "generate_audio": False, "duration": 4,
                                 "input_references": [img_ref(img["momon"]), img_ref(img["ruang"])], "prompt": "Momon the orange cat walks across the living room."}),
    ]
    # 3. referensi audio: coba beberapa bentuk tipe
    audio_forms = {
        "t3a_audio_url": {"type": "audio_url", "audio_url": {"url": url_a}},
        "t3b_input_audio": {"type": "input_audio", "input_audio": {"url": url_a}},
    }
    for name, ref in audio_forms.items():
        pg.append((name, {**base, "duration": 5, "input_references": [img_ref(img["momon"]), ref],
                          "prompt": "Momon the orange cat (@Image 1) speaks with the voice of @Audio 1, in the living room. Cartoon style."}))

    print("== job Seedance (satu per satu agar penyebab penolakan jelas) ==")
    done: dict[str, dict] = {}
    for name, payload in pg:
        row = run_job(client, name, payload, out)
        results.append(row)
        done[name] = row

    # 7. edit video: video hasil t1a sebagai video_url + instruksi edit
    print("== 7. edit video ==")
    src = done.get("t1a_at", {})
    if src.get("status") == "completed" and src.get("urls"):
        results.append(run_job(client, "t7a_edit", {**base, "duration": 5,
                               "input_references": [{"type": "video_url", "video_url": {"url": src["urls"][0]}}],
                               "prompt": "Edit this video: change only Momon's scarf from blue to red. Keep everything else exactly the same."}, out))
    else:
        notes["t7"] = "dilewati: t1a tidak selesai"

    pub.delete(key_a)
    getattr(pub, "close", lambda: None)()
    total = sum(v for v in costs.values() if v)
    summary = {"results": results, "costs": costs, "notes": notes, "total_usd": round(total, 4)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"total ${total:.4f}  -> {out/'summary.json'}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
