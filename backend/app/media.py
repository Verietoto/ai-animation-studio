import base64
import io
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError

MAX_SIDE = 2048


class MediaError(Exception):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def normalize_image(data: bytes) -> tuple[bytes, int, int]:
    """Tipe ditentukan dari isi file; EXIF diputar, RGB, sisi terpanjang <= MAX_SIDE, keluaran PNG."""
    try:
        img = Image.open(io.BytesIO(data))
        if getattr(img, "is_animated", False):
            raise MediaError("gambar animasi tidak didukung")
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            rgba = img.convert("RGBA")
            bg = Image.new("RGB", rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.split()[3])
            img = bg
        else:
            img = img.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise MediaError("file bukan gambar yang valid") from exc
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue(), img.width, img.height


def to_data_url(data: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def from_data_url(url: str, max_bytes: int) -> bytes:
    if not url.startswith("data:") or "," not in url:
        raise MediaError("bukan data URL")
    payload = url.split(",", 1)[1]
    if len(payload) > max_bytes * 4 // 3 + 16:
        raise MediaError("gambar hasil terlalu besar")
    try:
        return base64.b64decode(payload, validate=True)
    except ValueError as exc:
        raise MediaError("base64 tidak valid") from exc


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MediaError(proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "ffmpeg gagal")
    return proc


def probe(path: Path) -> dict:
    proc = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)])
    info = json.loads(proc.stdout)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise MediaError("file tidak berisi video")
    has_audio = any(s.get("codec_type") == "audio" for s in info["streams"])
    return {
        "width": int(video["width"]),
        "height": int(video["height"]),
        "duration": float(info["format"].get("duration", 0)),
        "has_audio": has_audio,
    }


def _is_usable(png: Path) -> bool:
    with Image.open(png) as img:
        return ImageStat.Stat(img.convert("L")).mean[0] > 12  # bukan frame hitam/fade-out


def extract_last_frame(video: Path, out_png: Path) -> None:
    """Ambil frame dekat akhir; mundur bila frame hitam (fade-out)."""
    last_error = None
    for offset in (0.1, 0.5, 1.0, 2.0):
        try:
            _run(["ffmpeg", "-y", "-v", "error", "-sseof", f"-{offset}", "-i", str(video),
                  "-frames:v", "1", "-update", "1", str(out_png)])
        except MediaError as exc:
            last_error = exc
            continue
        if out_png.exists() and _is_usable(out_png):
            return
    raise MediaError(f"tidak ada frame akhir yang layak: {last_error or 'semua frame gelap'}")


def merge_videos(inputs: list[Path], out: Path) -> None:
    """Samakan profil (resolusi, fps, codec, audio) lalu gabungkan tanpa re-encode ulang."""
    if not inputs:
        raise MediaError("tidak ada klip")
    first = probe(inputs[0])
    w, h = first["width"] // 2 * 2, first["height"] // 2 * 2
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, src in enumerate(inputs):
            info = probe(src)
            dst = Path(tmp) / f"p{i}.mp4"
            vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                  f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,format=yuv420p")
            cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
            if not info["has_audio"]:
                cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest"]
            cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", "-ar", "48000", "-ac", "2", "-map", "0:v:0",
                    "-map", "0:a:0" if info["has_audio"] else "1:a:0", str(dst)]
            _run(cmd)
            parts.append(dst)
        listing = Path(tmp) / "list.txt"
        listing.write_text("".join(f"file '{p}'\n" for p in parts))
        _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
              "-c", "copy", str(out)])
