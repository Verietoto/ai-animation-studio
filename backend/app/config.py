import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    base_url: str
    data_dir: Path
    daily_budget_usd: float
    poll_interval: float
    job_timeout: float
    max_upload_bytes: int
    max_chain: int
    max_cost_per_job: float = 1.0
    max_reference_seconds: float = 10.0
    max_video_upload_bytes: int = 200 * 1024 * 1024
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "auto"
    public_url_ttl: int = 3600

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_key=os.getenv("OPENROUTER_API_KEY") or None,
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            data_dir=Path(os.getenv("DATA_DIR", "./data")).resolve(),
            daily_budget_usd=float(os.getenv("DAILY_BUDGET_USD", "5")),
            poll_interval=float(os.getenv("POLL_INTERVAL_SECONDS", "5")),
            job_timeout=float(os.getenv("JOB_TIMEOUT_SECONDS", "1800")),
            max_upload_bytes=int(float(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024),
            max_chain=int(os.getenv("MAX_EXTEND_CHAIN", "6")),
            max_cost_per_job=float(os.getenv("MAX_COST_PER_JOB_USD", "1")),
            max_reference_seconds=float(os.getenv("MAX_REFERENCE_SECONDS", "10")),
            max_video_upload_bytes=int(float(os.getenv("MAX_VIDEO_UPLOAD_MB", "200")) * 1024 * 1024),
            s3_endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
            s3_bucket=os.getenv("S3_BUCKET") or None,
            s3_access_key_id=os.getenv("S3_ACCESS_KEY_ID") or None,
            s3_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY") or None,
            s3_region=os.getenv("S3_REGION", "auto"),
            public_url_ttl=int(os.getenv("PUBLIC_URL_TTL_SECONDS", "3600")),
        )
