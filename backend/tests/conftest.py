import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.services.cache import answer_cache
from app.services.telemetry import recorder


@pytest.fixture(autouse=True)
def _reset_telemetry():
    recorder.clear()
    yield


@pytest.fixture(autouse=True)
def _no_network_verify(monkeypatch):
    """Verification makes a live LLM call; off by default in tests."""
    monkeypatch.setattr(settings, "verify_answers", False)
    yield


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    answer_cache.clear()
    yield TestingSession()
    app.dependency_overrides.clear()


@pytest.fixture()
def client(db_session):
    # no context manager: skip lifespan so init_db() never touches a real db file
    return TestClient(app)


@pytest.fixture()
def auth_client(client):
    email = f"{uuid.uuid4().hex}@example.com"
    resp = client.post(
        "/api/auth/signup", json={"email": email, "password": "password123"}
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
