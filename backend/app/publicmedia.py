"""Menyajikan berkas lokal lewat URL HTTPS publik berumur pendek (video referensi harus URL publik).

Implementasi: S3-compatible (Cloudflare R2, S3, MinIO) dengan presigned GET URL. Objek privat,
nama acak, dihapus setelah job selesai dan oleh pembersih saat startup (plus aturan lifecycle bucket).
"""
import time
import uuid
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
