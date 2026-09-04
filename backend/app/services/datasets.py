"""Dataset persistence: metadata in SQLite, raw bytes in pluggable blob storage.

DataFrames and profiles are held in a small in-process LRU so repeated
questions on the same dataset don't re-fetch/parse the file every time.
"""
from __future__ import annotations

import uuid
from pathlib import PurePosixPath

import pandas as pd
from sqlalchemy.orm import Session

from app.models import DatasetRecord
from app.services.cache import TTLCache
from app.services.parser import SUPPORTED_EXTENSIONS, parse_bytes
from app.services.profiler import profile_dataframe
from app.services.storage import get_storage

_df_cache = TTLCache(max_entries=32, ttl_seconds=3600)
_profile_cache = TTLCache(max_entries=64, ttl_seconds=3600)

# DatasetRecord.filename is String(255). SQLite ignores the width; Postgres
# raises, so an over-long upload name would 500 in production only.
MAX_FILENAME_CHARS = 255


def _basename(filename: str) -> str:
    """Last path segment, treating both separators -- the client picks either."""
    return PurePosixPath(filename.replace("\\", "/")).name


def _storage_key(dataset_id: str, filename: str) -> str:
    """Blob key built from the dataset id and the *extension* only.

    The uploaded filename is attacker-controlled and must never reach the key.
    A name like `"../<other-dataset-id>/data.csv"` resolves back *inside* the
    storage root, so a containment check alone still lets one user overwrite
    another user's file and swap the data under their questions. The name the
    user sees is kept in DatasetRecord.filename, which is never a path.
    """
    ext = PurePosixPath(_basename(filename)).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        ext = ".bin"  # not reachable via upload: parse_bytes rejects these first
    return f"{dataset_id}/data{ext}"


def _display_name(filename: str) -> str:
    return _basename(filename)[:MAX_FILENAME_CHARS] or "upload"


def create_dataset(db: Session, owner_id: str, raw: bytes, filename: str) -> DatasetRecord:
    df = parse_bytes(raw, filename)  # validate before we persist anything

    dataset_id = uuid.uuid4().hex
    key = _storage_key(dataset_id, filename)
    get_storage().save(key, raw)

    record = DatasetRecord(
        id=dataset_id,
        owner_id=owner_id,
        filename=_display_name(filename),
        path=key,
        n_rows=int(df.shape[0]),
        n_cols=int(df.shape[1]),
    )
    db.add(record)
    db.commit()

    _df_cache.set(dataset_id, df)
    return record


def get_record(db: Session, dataset_id: str, owner_id: str) -> DatasetRecord | None:
    return (
        db.query(DatasetRecord)
        .filter(DatasetRecord.id == dataset_id, DatasetRecord.owner_id == owner_id)
        .first()
    )


def list_records(db: Session, owner_id: str) -> list[DatasetRecord]:
    return (
        db.query(DatasetRecord)
        .filter(DatasetRecord.owner_id == owner_id)
        .order_by(DatasetRecord.created_at.desc())
        .all()
    )


def load_df(record: DatasetRecord) -> pd.DataFrame:
    cached = _df_cache.get(record.id)
    if cached is not None:
        return cached
    raw = get_storage().load(record.path)
    df = parse_bytes(raw, record.filename)
    _df_cache.set(record.id, df)
    return df


def get_profile(record: DatasetRecord) -> dict:
    cached = _profile_cache.get(record.id)
    if cached is not None:
        return cached
    profile = profile_dataframe(load_df(record))
    _profile_cache.set(record.id, profile)
    return profile


def delete_dataset(db: Session, record: DatasetRecord) -> None:
    key = record.path
    db.delete(record)
    db.commit()
    _df_cache.set(record.id, None)
    _profile_cache.set(record.id, None)
    try:
        get_storage().delete(key)
    except Exception:  # noqa: BLE001 - metadata is already gone; storage cleanup is best-effort
        pass
