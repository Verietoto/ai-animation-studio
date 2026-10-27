"""Plan 10: server berkas + tunnel sementara. Tunnel palsu; server berkas diuji nyata di 127.0.0.1."""
import time
import urllib.error
import urllib.request

import pytest

from app.publicmedia import PublicMediaError, TunnelPublicMedia, parse_range

DATA = bytes(range(256)) * 40   # 10240 byte


class FakeProc:
    def __init__(self):
        self.stopped = False

    def poll(self):
        return 0 if self.stopped else None

    def terminate(self):
        self.stopped = True

    def wait(self, t=None):
        pass

    def kill(self):
        self.stopped = True


@pytest.fixture
def media(tmp_path):
    started = []

    def starter(port):
        started.append(port)
        return f"http://127.0.0.1:{port}", FakeProc()   # tunnel palsu: URL dasar = server lokal
    m = TunnelPublicMedia(ttl=3600, starter=starter, idle_seconds=0.4)
    m.started = started
    yield m
    m.close()


@pytest.fixture
def video(tmp_path):
    p = tmp_path / "ref.mp4"
    p.write_bytes(DATA)
    return p


def get(url, headers=None, method="GET"):
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, b"", dict(e.headers)


def test_serves_only_registered_file_with_full_body(media, video):
    key, url = media.publish(video)
    assert len(key) == 32 and url.endswith(f"/{key}.mp4")
    status, body, headers = get(url)
    assert status == 200 and body == DATA and headers["Accept-Ranges"] == "bytes"
    assert get(url, method="HEAD")[0] == 200
    base = url.rsplit("/", 1)[0]
    for bad in ("/", "/abc.mp4", "/" + "0" * 32 + ".mp4", "/../etc/passwd", f"/{key}/../{key}x.mp4", "/%2e%2e/x"):
        assert get(base + bad)[0] == 404, bad


def test_range_requests(media, video):
    _, url = media.publish(video)
    s, body, h = get(url, {"Range": "bytes=10-19"})
    assert s == 206 and body == DATA[10:20] and h["Content-Range"] == f"bytes 10-19/{len(DATA)}"
    assert get(url, {"Range": "bytes=10000-"})[1] == DATA[10000:]
    assert get(url, {"Range": "bytes=-5"})[1] == DATA[-5:]
    assert get(url, {"Range": "bytes=99999-"})[0] == 416
    assert get(url, {"Range": "bytes=abc"})[0] == 416


def test_parse_range_rules():
    assert parse_range(None, 100) is None
    assert parse_range("bytes=0-", 100) == (0, 99)
    assert parse_range("bytes=90-500", 100) == (90, 99)
    assert parse_range("bytes=-10", 100) == (90, 99)
    for bad in ("bytes=-", "bytes=5-2", "bytes=100-", "bytes=-0", "items=1-2"):
        with pytest.raises(ValueError):
            parse_range(bad, 100)


def test_delete_and_expiry_stop_serving(media, video):
    key, url = media.publish(video)
    media.delete(key)
    assert get(url)[0] == 404
    key2, url2 = media.publish(video)
    media._files[key2] = (video, time.time() - 1)
    assert get(url2)[0] == 404
    key3, _ = media.publish(video)
    media._files[key3] = (video, time.time() - 1)
    assert media.cleanup(0) == 1


def test_missing_file_is_404_not_crash(media, video):
    _, url = media.publish(video)
    video.unlink()
    assert get(url)[0] == 404
    with pytest.raises(PublicMediaError):
        media.publish(video)


def test_single_tunnel_for_many_publishes_and_unique_tokens(media, video):
    keys = {media.publish(video)[0] for _ in range(5)}
    assert len(keys) == 5 and len(media.started) == 1


def test_tunnel_failure_is_reported_clearly(video):
    def boom(port):
        raise PublicMediaError("tunnel cloudflared tidak naik dalam 30 detik")
    m = TunnelPublicMedia(ttl=3600, starter=boom)
    with pytest.raises(PublicMediaError, match="tidak naik"):
        m.publish(video)
    def odd(port):
        raise OSError("x")
    with pytest.raises(PublicMediaError, match="gagal menyalakan tunnel"):
        TunnelPublicMedia(ttl=3600, starter=odd).publish(video)


def test_tunnel_stops_when_idle_and_restarts(media, video):
    key, _ = media.publish(video)
    proc = media._proc
    media.delete(key)
    deadline = time.time() + 5
    while media._proc is not None and time.time() < deadline:
        time.sleep(0.1)
    assert media._proc is None and proc.stopped
    media.publish(video)
    assert len(media.started) == 2


def test_close_stops_tunnel(media, video):
    media.publish(video)
    proc = media._proc
    media.close()
    assert proc.stopped and media._server is None


def test_create_app_selects_tunnel_only_when_configured(settings, fake, tmp_path, monkeypatch):
    import dataclasses
    import httpx
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.openrouter import OpenRouterClient

    def health(tunnel, which):
        monkeypatch.setattr("app.main.shutil.which", lambda name: which)
        st = dataclasses.replace(settings, public_tunnel=tunnel, data_dir=tmp_path / f"d{tunnel}{which}")
        client = OpenRouterClient(st.api_key, st.base_url, transport=httpx.MockTransport(fake))
        with TestClient(create_app(st, client)) as tc:
            return tc.get("/api/health").json()["public_media"]
    assert health(None, "/usr/bin/cloudflared") is False
    assert health("cloudflared", None) is False
    assert health("cloudflared", "/usr/bin/cloudflared") is True


def test_wait_reachable_local_http_accepts_any_answer_and_gives_up(media, video):
    from app.publicmedia import wait_reachable
    media.publish(video)
    assert wait_reachable(media._base, timeout=3) is True   # 404 dari /ping tetap berarti terjangkau
    assert wait_reachable("http://127.0.0.1:9", timeout=0.5) is False


def test_https_probe_never_uses_local_dns(monkeypatch):
    """Resolver lokal men-cache NXDOMAIN ±75 dtk; pengecekan alamat https harus lewat DoH + sambung ke IP."""
    from app import publicmedia as pm
    calls = []
    monkeypatch.setattr(pm.socket, "getaddrinfo", lambda *a, **k: calls.append("lokal"))
    answers = iter([[], [], ["104.16.0.1"]])
    monkeypatch.setattr(pm, "_doh_ips", lambda host: next(answers))
    monkeypatch.setattr(pm, "_answers_https", lambda ip, host: ip == "104.16.0.1")
    monkeypatch.setattr(pm.time, "sleep", lambda s: None)
    assert pm.wait_reachable("https://abc.trycloudflare.com", timeout=30) is True
    assert calls == []
    monkeypatch.setattr(pm, "_doh_ips", lambda host: None)   # DoH diblokir: lanjut setelah jeda singkat
    assert pm.wait_reachable("https://abc.trycloudflare.com", timeout=30) is True


def test_not_ready_keeps_tunnel_alive_and_next_publish_reprobes(video):
    results = iter([False, True])
    started = []
    m = TunnelPublicMedia(ttl=3600, probe=lambda base: next(results),
                          starter=lambda port: (started.append(port) or f"http://127.0.0.1:{port}", FakeProc()))
    try:
        with pytest.raises(PublicMediaError, match="belum melayani"):
            m.publish(video)
        assert m._proc is not None and not m._proc.stopped   # tunnel tidak dimatikan
        key, _ = m.publish(video)   # percobaan kedua memakai tunnel yang sama
        assert len(started) == 1 and key
    finally:
        m.close()
