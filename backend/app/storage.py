import uuid
from pathlib import Path


class Storage:
    """Penyimpanan lokal. Nama file selalu UUID; path tidak pernah dari input user."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def new_path(self, suffix: str) -> Path:
        return self.root / f"{uuid.uuid4().hex}{suffix}"

    def save(self, data: bytes, suffix: str) -> Path:
        path = self.new_path(suffix)
        path.write_bytes(data)
        return path

    def resolve(self, stored: str) -> Path:
        path = Path(stored).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("path di luar storage")
        return path
