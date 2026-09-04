"""Pluggable blob storage for uploaded dataset files.

- LocalStorage (default): files under backend/uploads/. Zero config; use for
  local development and debugging.
- S3Storage: any S3-compatible target (AWS S3, Supabase Storage, MinIO).
  Enable with STORAGE_BACKEND=s3 plus S3_BUCKET (+ optional S3_ENDPOINT_URL).

Both expose the same interface, keyed by an opaque string `key`:
    save(key, data) -> None
    load(key) -> bytes
    delete(key) -> None
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import settings

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"

_UNSAFE_SEGMENTS = frozenset({"", ".", ".."})


def validate_key(key: str) -> str:
    """Reject any key that is not a plain relative path of ordinary segments.

    Keys are built in `services/datasets._storage_key` and never contain user
    input beyond a validated extension -- this is the backstop for that, and it
    is a *segment* check rather than a containment check on purpose. A key like
    `"<a>/../<b>/data.csv"` resolves to a path that is still inside the storage
    root, so containment alone would happily let one dataset clobber another.
    """
    segments = key.replace("\\", "/").split("/")
    if not key or any(seg in _UNSAFE_SEGMENTS for seg in segments):
        raise ValueError(f"Unsafe storage key: {key!r}")
    return key


class Storage(Protocol):
    def save(self, key: str, data: bytes) -> None: ...
    def load(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path = UPLOAD_DIR) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Keys look like "<dataset_id>/data.csv". Two independent checks: the
        # segment rules above, then containment, which still catches absolute
        # keys and Windows drive letters that survive the split.
        p = (self.root / validate_key(key)).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError(f"Unsafe storage key: {key!r}")
        return p

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def load(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()
        parent = path.parent
        if parent != self.root and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()


class S3Storage:
    def __init__(self) -> None:
        if not settings.s3_bucket:
            raise RuntimeError("STORAGE_BACKEND=s3 requires S3_BUCKET to be set.")
        import boto3

        self.bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.s3_region,
        )

    def save(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self.bucket, Key=validate_key(key), Body=data)

    def load(self, key: str) -> bytes:
        obj = self._client.get_object(Bucket=self.bucket, Key=validate_key(key))
        return obj["Body"].read()

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=validate_key(key))


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    if settings.storage_backend == "s3":
        return S3Storage()
    return LocalStorage()
