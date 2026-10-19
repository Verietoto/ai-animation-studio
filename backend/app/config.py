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
        )
