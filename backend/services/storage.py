"""Pluggable storage provider for uploaded datasets with content hashing."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from pathlib import Path

from backend.config import PROJECT_ROOT


def compute_sha256(content: bytes) -> str:
    """Compute SHA-256 hex digest of file contents for deduplication."""
    return hashlib.sha256(content).hexdigest()


class StorageProvider(ABC):
    @abstractmethod
    def save(self, content: bytes, destination_path: str) -> str:
        """Save file bytes and return access path or URI."""
        ...

    @abstractmethod
    def load(self, source_path: str) -> bytes:
        """Load file bytes from storage."""
        ...


class LocalStorageProvider(StorageProvider):
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or (PROJECT_ROOT / "data" / "uploads")

    def save(self, content: bytes, destination_path: str) -> str:
        target = self.base_dir / destination_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return str(target)

    def load(self, source_path: str) -> bytes:
        path = Path(source_path)
        if not path.is_absolute():
            path = self.base_dir / source_path
        return path.read_bytes()


def get_storage_provider() -> StorageProvider:
    """Return configured storage provider (default: local filesystem)."""
    return LocalStorageProvider()
