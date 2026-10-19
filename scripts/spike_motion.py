"""Spike plan 03 (BERBIAYA): menguji jalur transfer gerakan di OpenRouter.

Pemakaian bertahap (hasil tiap tahap dilihat manusia):
  refvideo            buat video referensi dari gambar orang (Grok lite, murah)
  submit NAMA MODEL   kirim job dengan video referensi sebagai input_references (video_url)
  poll NAMA           tunggu job, simpan hasil dan catat biaya
Anggaran dijaga lewat file state (SPIKE_CAP_USD, default 3.5); script berhenti bila terlampaui.
"""
import base64, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app import media  # noqa: E402
from app.openrouter import OpenRouterClient, OpenRouterError  # noqa: E402

D = os.environ.get("SPIKE_DIR", "/tmp/claude-0/spike/")
CAP = float(os.getenv("SPIKE_CAP_USD", "3.5"))
c = OpenRouterClient(os.environ["OPENROUTER_API_KEY"], "https://openrouter.ai/api/v1")
STATE = D + "state.json"


def load(): return json.load(open(STATE))
def save(s): json.dump(s, open(STATE, "w"), indent=1)


def guard(extra):
    s = load()
    if s["spent"] + extra > CAP:
        sys.exit(f"STOP: anggaran spike ${CAP} akan terlampaui (terpakai {s['spent']:.3f} + estimasi {extra})")


def wait(job_id, every=8, limit=900):
    t0 = time.time()
    while time.time() - t0 < limit:
        j = c.get_video_job(job_id)
        print(" status:", j.get("status"), flush=True)
        if j.get("status") in ("completed", "failed", "cancelled"):
            return j
        time.sleep(every)
    sys.exit("timeout")


def data_url(path): return media.to_data_url(open(path, "rb").read())


def finish(name, job):
    s = load()
    cost = (job.get("usage") or {}).get("cost") or 0
    s["spent"] += cost
    s.setdefault("jobs", {}).setdefault(name, {}).update(status=job["status"], cost=cost, error=job.get("error"),
                                                       urls=job.get("urls"), keys=sorted(job.keys()))
    if job["status"] == "completed":
        open(D + f"{name}.mp4", "wb").write(c.download_video(job["id"]))
    save(s)
    print(f"{name}: {job['status']} cost={cost} spent_total={s['spent']:.3f} error={job.get('error')}")
    print(" job keys:", sorted(job.keys()))
    if job.get("urls"): print(" public urls present:", len(job["urls"]), "expires_at" in job and job.get("expires_at"))


cmd = sys.argv[1]
if cmd == "refvideo":
    guard(0.2)
    r = c.submit_video({"model": "x-ai/grok-imagine-video-1.5-lite", "duration": 5, "resolution": os.getenv("REF_RES", "720p"), "aspect_ratio": "16:9",
                        "prompt": "Static camera. The man raises his right hand and waves twice, then turns his body to his left, then jumps once with both feet, then stands still again.",
                        "frame_images": [{"type": "image_url", "image_url": {"url": data_url(D + os.getenv("REF_IMG", "ref_person.png"))}, "frame_type": "first_frame"}]})
    name = os.getenv("REF_NAME", "ref")
    s = load(); s.setdefault("jobs", {})[name] = {"id": r["id"]}; save(s)
    finish(name, wait(r["id"]) | {"id": r["id"]})
elif cmd == "submit":
    name, model = sys.argv[2], sys.argv[3]
    extra = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
    guard(float(os.getenv("EST", "0.5")))
    s = load()
    ref_url = c.get_video_job(s["jobs"][os.getenv("REF_JOB", "ref")]["id"])["urls"][0]   # URL publik bertanda tangan muncul beberapa saat setelah selesai
    body = {"model": model, **extra.pop("body", {}), "prompt": extra.pop("prompt")}
    refs = [{"type": "video_url", "video_url": {"url": ref_url}}]
    for img in extra.pop("images", []):
        refs.append({"type": "image_url", "image_url": {"url": data_url(D + img)}})
    body[extra.pop("field", "input_references")] = refs
    body.update(extra)
    try:
        r = c.submit_video(body)
    except OpenRouterError as exc:
        print("SUBMIT ERROR:", exc); s["jobs"][name] = {"status": "rejected", "error": str(exc)}; save(s); sys.exit(0)
    s["jobs"][name] = {"id": r["id"], "model": model, "status": "submitted"}; save(s)
    print("submitted", r)
elif cmd == "poll":
    name = sys.argv[2]
    jid = load()["jobs"][name]["id"]
    finish(name, wait(jid) | {"id": jid})
