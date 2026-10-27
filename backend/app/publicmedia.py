"""Menyajikan berkas lokal lewat URL HTTPS publik berumur pendek (video referensi harus URL publik).

Implementasi: S3-compatible (Cloudflare R2, S3, MinIO) dengan presigned GET URL. Objek privat,
nama acak, dihapus setelah job selesai dan oleh pembersih saat startup (plus aturan lifecycle bucket).
"""
import json
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class PublicMediaError(Exception):
    pass


class NoPublicMedia:
    def publish(self, path: Path, content_type: str = "video/mp4") -> tuple[str, str]:
        raise PublicMediaError("hosting URL publik belum dikonfigurasi (S3_ENDPOINT_URL, S3_BUCKET, "
                               "S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY); gunakan klip dari library sebagai referensi")

    def delete(self, key: str) -> None:
        pass

    def cleanup(self, older_than_seconds: int) -> int:
        return 0


class S3PublicMedia:
    PREFIX = "refs/"

    def __init__(self, endpoint_url: str | None, bucket: str, access_key_id: str, secret_access_key: str,
                 region: str, ttl: int, client=None):
        if client is None:
            import boto3   # impor tertunda: hanya perlu bila S3 dipakai
            client = boto3.client("s3", endpoint_url=endpoint_url, aws_access_key_id=access_key_id,
                                  aws_secret_access_key=secret_access_key, region_name=region)
        self.client, self.bucket, self.ttl = client, bucket, ttl

    def publish(self, path: Path, content_type: str = "video/mp4") -> tuple[str, str]:
        key = f"{self.PREFIX}{uuid.uuid4().hex}{path.suffix}"
        try:
            self.client.upload_file(str(path), self.bucket, key, ExtraArgs={"ContentType": content_type})
            url = self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key},
                                                     ExpiresIn=self.ttl)
        except Exception as exc:   # kredensial salah, bucket tak ada, jaringan
            raise PublicMediaError(f"gagal menyajikan berkas ke storage publik: {type(exc).__name__}") from exc
        return key, url

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception:
            pass

    def cleanup(self, older_than_seconds: int) -> int:
        """Hapus objek refs/ yang lebih tua dari batas (sisa job yang tak sempat dibersihkan)."""
        removed, cutoff = 0, time.time() - older_than_seconds
        try:
            for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=self.PREFIX):
                for obj in page.get("Contents", []):
                    if obj["LastModified"].timestamp() < cutoff:
                        self.client.delete_object(Bucket=self.bucket, Key=obj["Key"])
                        removed += 1
        except Exception:
            pass
        return removed


# ---------- tunnel sementara (plan 10) ----------
TUNNEL_URL = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com")
IDLE_SECONDS = 300


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """'bytes=a-b' / 'bytes=a-' / 'bytes=-n' -> (awal, akhir) inklusif. None = tanpa Range; ValueError = tak valid (416)."""
    if not header:
        return None
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if not m or (not m.group(1) and not m.group(2)):
        raise ValueError("range")
    if not m.group(1):   # suffix: n byte terakhir
        n = int(m.group(2))
        if n == 0:
            raise ValueError("range")
        return max(size - n, 0), size - 1
    start = int(m.group(1))
    end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
    if start >= size or end < start:
        raise ValueError("range")
    return start, end


def start_cloudflared(port: int, timeout: float = 30.0) -> tuple[str, "subprocess.Popen"]:
    """Jalankan quick tunnel ke 127.0.0.1:port; kembalikan (url_publik, proses)."""
    exe = shutil.which("cloudflared")
    if not exe:
        raise PublicMediaError("cloudflared tidak ditemukan di PATH (brew install cloudflared)")
    proc = subprocess.Popen([exe, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    found: list[str] = []
    ready = threading.Event()

    def drain():   # stderr harus terus dikuras, kalau tidak cloudflared bisa tersumbat
        for line in proc.stderr:
            if not found and (m := TUNNEL_URL.search(line)):
                found.append(m.group(0))
                ready.set()
        ready.set()   # proses berhenti sebelum URL muncul
    threading.Thread(target=drain, daemon=True).start()
    ready.wait(timeout)
    if not found:
        proc.kill()
        raise PublicMediaError("tunnel cloudflared tidak naik dalam 30 detik (cek koneksi internet)")
    return found[0], proc


def _doh_ips(host: str) -> list[str] | None:
    """Alamat A dari DNS publik Cloudflare (DoH). [] = belum ada; None = DoH sendiri tidak bisa dipakai."""
    req = urllib.request.Request(f"https://cloudflare-dns.com/dns-query?name={host}&type=A", headers={"accept": "application/dns-json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return [a["data"] for a in json.load(r).get("Answer", []) if a.get("type") == 1]
    except Exception:
        return None


def _answers_https(ip: str, host: str) -> bool:
    """Sambung ke IP dengan SNI host; respons HTTP apa pun (404 juga) berarti tunnel melayani."""
    try:
        with socket.create_connection((ip, 443), timeout=5) as raw, \
                ssl.create_default_context().wrap_socket(raw, server_hostname=host) as tls:
            tls.sendall(f"GET /ping HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
            return tls.recv(12).startswith(b"HTTP/")
    except Exception:
        return False


def wait_reachable(base: str, timeout: float = 90.0) -> bool:
    """Tunggu sampai alamat tunnel benar-benar melayani.

    Alamat https TIDAK dicek lewat DNS lokal: pertanyaan pertama yang dijawab NXDOMAIN ikut di-cache resolver lokal
    (terukur ±75 dtk di resolver 8.8.8.8, padahal 1.1.1.1 mengenalinya dalam 1 dtk) dan itu bukan sudut pandang penyedia.
    Dipakai DoH Cloudflare lalu sambung langsung ke IP. Bila DoH tak bisa dipakai: tunggu singkat, anggap siap.
    """
    deadline = time.time() + timeout
    if base.startswith("https://"):
        host = base[len("https://"):]
        while time.time() < deadline:
            ips = _doh_ips(host)
            if ips is None:   # jaringan memblokir DoH: tak bisa diperiksa, beri waktu lalu lanjut
                time.sleep(min(10, max(deadline - time.time(), 0)))
                return True
            if ips and any(_answers_https(ip, host) for ip in ips):
                return True
            time.sleep(1)
        return False
    while time.time() < deadline:   # http lokal (tes): resolver lokal aman
        try:
            urllib.request.urlopen(f"{base}/ping", timeout=5)
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            time.sleep(0.5)
    return False


class TunnelPublicMedia:
    """Menyajikan berkas lewat server lokal kecil + quick tunnel cloudflared (tanpa akun).

    Hanya token yang didaftarkan yang dilayani (GET/HEAD, Range didukung); aplikasi utama tidak ikut terbuka.
    Pemetaan token hanya di memori: restart backend memutus job yang sedang berjalan.
    """

    def __init__(self, ttl: int, starter=start_cloudflared, idle_seconds: float = IDLE_SECONDS, probe=wait_reachable):
        self.ttl, self.starter, self.idle, self.probe = max(ttl, 7200), starter, idle_seconds, probe
        self._verified = False
        self._files: dict[str, tuple[Path, float]] = {}
        self._lock = threading.RLock()
        self._server: ThreadingHTTPServer | None = None
        self._proc = None
        self._base: str | None = None
        self._idle_since: float | None = None
        self._closed = threading.Event()

    # ---- server berkas ----
    def _lookup(self, token: str) -> Path | None:
        with self._lock:
            item = self._files.get(token)
            if item and item[1] > time.time():
                return item[0]
            self._files.pop(token, None)
        return None

    def _make_server(self) -> ThreadingHTTPServer:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):   # jangan mencatat URL (berisi token) ke log
                pass

            def _serve(self, head: bool):
                try:
                    token = self.path.split("?")[0].strip("/").split(".")[0]
                    path = outer._lookup(token) if re.fullmatch(r"[0-9a-f]{32}", token) else None
                    if not path or not path.is_file():
                        return self._plain(404)
                    size = path.stat().st_size
                    try:
                        rng = parse_range(self.headers.get("Range"), size)
                    except ValueError:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        return self.end_headers()
                    start, end = rng if rng else (0, size - 1)
                    self.send_response(206 if rng else 200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(end - start + 1))
                    if rng:
                        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                    self.end_headers()
                    if head:
                        return
                    with open(path, "rb") as fh:
                        fh.seek(start)
                        left = end - start + 1
                        while left > 0 and (chunk := fh.read(min(1 << 20, left))):
                            self.wfile.write(chunk)
                            left -= len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception:   # satu request buruk tidak boleh mematikan server
                    try:
                        self._plain(500)
                    except Exception:
                        pass

            def _plain(self, code: int):
                self.send_response(code)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                self._serve(False)

            def do_HEAD(self):
                self._serve(True)

        return ThreadingHTTPServer(("127.0.0.1", 0), Handler)

    def _ensure(self) -> str:
        with self._lock:   # satu tunnel saja walau banyak publish bersamaan
            alive = self._base and (self._proc is None or self._proc.poll() is None)
            if not alive:
                self._stop_locked()
                self._verified = False
                server = self._make_server()
                threading.Thread(target=server.serve_forever, daemon=True).start()
                try:
                    self._base, self._proc = self.starter(server.server_address[1])
                except Exception:
                    server.shutdown()
                    server.server_close()
                    raise
                self._server = server
                self._closed.clear()
                threading.Thread(target=self._idle_loop, daemon=True).start()
            if not self._verified:   # bila belum siap, tunnel TETAP hidup supaya percobaan berikutnya tidak mulai dari nol
                if not self.probe(self._base):
                    raise PublicMediaError("tunnel naik tetapi alamat publiknya belum melayani; tunggu beberapa detik lalu coba lagi")
                self._verified = True
            return self._base

    def _stop_locked(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(5)
            except Exception:
                self._proc.kill()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        self._proc = self._server = self._base = None

    def _idle_loop(self) -> None:
        while not self._closed.wait(min(self.idle / 4, 30)):
            with self._lock:
                now = time.time()
                self._files = {k: v for k, v in self._files.items() if v[1] > now}
                if self._files:
                    self._idle_since = None
                elif self._idle_since is None:
                    self._idle_since = now
                elif now - self._idle_since >= self.idle:
                    self._stop_locked()
                    return

    # ---- antarmuka PublicMedia ----
    def publish(self, path: Path, content_type: str = "video/mp4") -> tuple[str, str]:
        if not Path(path).is_file():
            raise PublicMediaError("berkas yang akan disajikan tidak ada")
        try:
            base = self._ensure()
        except PublicMediaError:
            raise
        except Exception as exc:
            raise PublicMediaError(f"gagal menyalakan tunnel: {type(exc).__name__}") from exc
        token = secrets.token_hex(16)
        with self._lock:
            self._files[token] = (Path(path), time.time() + self.ttl)
            self._idle_since = None
        return token, f"{base}/{token}{Path(path).suffix or '.mp4'}"

    def delete(self, key: str) -> None:
        with self._lock:
            self._files.pop(key, None)

    def cleanup(self, older_than_seconds: int) -> int:
        with self._lock:   # token hanya hidup di memori; yang kedaluwarsa dibuang
            now = time.time()
            gone = [k for k, v in self._files.items() if v[1] <= now]
            for k in gone:
                del self._files[k]
            return len(gone)

    def close(self) -> None:
        self._closed.set()
        with self._lock:
            self._files.clear()
            self._stop_locked()
