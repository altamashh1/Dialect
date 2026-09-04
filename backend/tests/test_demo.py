"""The public demo account: seeding, one-click sign-in, and its off switch."""
from __future__ import annotations

import pytest

from app.config import settings
from app.models import User
from app.services.demo import demo_login_id, seed_demo


@pytest.fixture()
def demo_on(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    yield


def test_demo_endpoint_is_absent_unless_enabled(client):
    """A deployment without a demo exposes no extra authentication surface."""
    assert client.post("/api/auth/demo").status_code == 404


def test_seed_demo_does_nothing_when_disabled(db_session):
    seed_demo(db_session)
    assert db_session.query(User).count() == 0


def test_seed_demo_creates_the_account(db_session, demo_on):
    seed_demo(db_session)
    user = db_session.query(User).filter(User.email == demo_login_id()).first()
    assert user is not None


def test_seed_demo_is_idempotent(db_session, demo_on):
    """Runs on every boot, so a restart must not pile up duplicate accounts."""
    seed_demo(db_session)
    seed_demo(db_session)
    seed_demo(db_session)
    assert db_session.query(User).filter(User.email == demo_login_id()).count() == 1


def test_demo_signin_returns_a_usable_token(client, db_session, demo_on):
    seed_demo(db_session)

    resp = client.post("/api/auth/demo")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == demo_login_id()

    # The token must actually authenticate, not merely be well-formed.
    me = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"}
    )
    assert me.status_code == 200


def test_demo_signin_needs_no_credentials(client, db_session, demo_on):
    """The password stays server-side; the frontend bundle never carries it."""
    seed_demo(db_session)
    assert client.post("/api/auth/demo", json={}).status_code == 200


def test_demo_signin_reports_unready_before_seeding(client, demo_on):
    assert client.post("/api/auth/demo").status_code == 503
