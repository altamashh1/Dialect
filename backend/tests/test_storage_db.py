"""DatabaseStorage: uploads persisted in the database, no object store needed."""
from __future__ import annotations

import pytest

from app.config import PERSISTENT_STORAGE_BACKENDS, Settings, check_production_readiness
from app.models import Blob
from app.services.storage import DatabaseStorage

KEY = "abc123/data.csv"
DATA = b"order_id,region\n1,North\n2,South\n"


@pytest.fixture()
def storage(db_session, monkeypatch):
    """Bind DatabaseStorage to the test session.

    It opens its own sessions in production; here it must reuse the in-memory
    one the fixture set up, and must not close it between calls.
    """
    import app.services.storage as mod

    monkeypatch.setattr(mod, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    return DatabaseStorage()


def test_round_trip(storage):
    s = storage
    s.save(KEY, DATA)
    assert s.load(KEY) == DATA


def test_overwrite_keeps_one_row(storage, db_session):
    s = storage
    s.save(KEY, DATA)
    s.save(KEY, b"replaced")
    assert s.load(KEY) == b"replaced"
    assert db_session.query(Blob).count() == 1


def test_delete_removes_the_row(storage, db_session):
    s = storage
    s.save(KEY, DATA)
    s.delete(KEY)
    assert db_session.query(Blob).count() == 0
    with pytest.raises(FileNotFoundError):
        s.load(KEY)


def test_delete_is_idempotent(storage):
    storage.delete("never/existed.csv")  # must not raise


def test_unsafe_keys_are_rejected(storage):
    """The same segment rules the other backends enforce."""
    s = storage
    for bad in ["../escape.csv", "a/../b.csv", "", "a//b.csv"]:
        with pytest.raises(ValueError):
            s.save(bad, DATA)


def test_db_counts_as_persistent_in_production():
    """A db-backed deploy needs no object store to pass the readiness gate."""
    assert "db" in PERSISTENT_STORAGE_BACKENDS

    s = Settings(
        environment="production",
        jwt_secret="x" * 40,
        storage_backend="db",
        database_url="postgresql+psycopg://user:pw@host/db",
        gemini_api_key="key",
        cors_origins="",
    )
    assert check_production_readiness(s) == []


def test_local_backend_still_fails_production():
    s = Settings(
        environment="production",
        jwt_secret="x" * 40,
        storage_backend="local",
        database_url="postgresql+psycopg://user:pw@host/db",
        gemini_api_key="key",
        cors_origins="",
    )
    problems = check_production_readiness(s)
    assert any("STORAGE_BACKEND" in p for p in problems)
