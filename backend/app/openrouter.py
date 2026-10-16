"""Klien tipis OpenRouter.

PENTING: bentuk request/respons di sini disusun dari dokumentasi publik dan BELUM
diuji terhadap API nyata (tidak ada API key saat pengembangan). Respons dibaca
secara longgar. Jalankan scripts/smoke_openrouter.py dengan key sungguhan untuk verifikasi.
"""
import re
from typing import Any

import httpx


class OpenRouterError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _clean(text: str, limit: int = 500) -> str:
    # jangan pernah membocorkan token ke log/UI
    text = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "[redacted]", text)
    return text[:limit]


class OpenRouterClient:
    def __init__(self, api_key: str | None, base_url: str, transport: httpx.BaseTransport | None = None):
        self.api_key = api_key
        self._http = httpx.Client(base_url=base_url, timeout=httpx.Timeout(60.0, read=300.0), transport=transport)

    def _request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        if not self.api_key:
            raise OpenRouterError("OPENROUTER_API_KEY belum diatur")
        try:
            resp = self._http.request(method, path, headers={"Authorization": f"Bearer {self.api_key}"}, **kw)
        except httpx.HTTPError as exc:
            raise OpenRouterError(_clean(f"gagal menghubungi OpenRouter: {exc}")) from exc
        if resp.status_code >= 400:
            raise OpenRouterError(_clean(f"OpenRouter {resp.status_code}: {resp.text}"), resp.status_code)
        return resp

    # --- video ---
    def list_video_models(self) -> list[dict]:
        return self._request("GET", "/videos/models").json().get("data", [])

    def submit_video(self, payload: dict) -> dict:
        return self._request("POST", "/videos", json=payload).json()

    def get_video_job(self, job_id: str) -> dict:
        return self._request("GET", f"/videos/{job_id}").json()

    def download_video(self, job_id: str, index: int = 0) -> bytes:
        data = self._request("GET", f"/videos/{job_id}/content", params={"index": index}).content
        if not data:
            raise OpenRouterError("konten video kosong")
        return data

    # --- image ---
    def list_image_models(self) -> list[dict]:
        models = self._request("GET", "/models", params={"output_modalities": "image"}).json().get("data", [])
        return [m for m in models if "image" in (m.get("architecture", {}).get("input_modalities") or ["image"])]

    def edit_image(self, model: str, prompt: str, image_urls: list[str]) -> dict:
        content = [{"type": "text", "text": prompt}] + [
            {"type": "image_url", "image_url": {"url": u}} for u in image_urls
        ]
        body = {"model": model, "modalities": ["image", "text"],
                "messages": [{"role": "user", "content": content}]}
        return self._request("POST", "/chat/completions", json=body).json()
