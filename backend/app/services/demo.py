"""Public demo account: one-click access for anyone visiting the deployed app.

Seeded during application startup rather than by a manual command, because the
free hosting tiers this is deployed on wipe the container filesystem on every
restart -- a demo that needs someone to SSH in and re-seed it is a demo that is
broken most of the time.

Idempotent by design: safe to run on every boot.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.auth import hash_password, new_user_id
from app.config import settings
from app.models import User
from app.services import datasets as store

# sample_sales.csv lives at the repository root. Render's "root directory"
# setting only changes the working directory -- the whole repo is still on
# disk -- but probe a few locations and degrade gracefully rather than failing
# a boot over a missing sample file.
_SAMPLE_CANDIDATES = (
    Path(__file__).resolve().parents[3] / "sample_sales.csv",
    Path.cwd() / "sample_sales.csv",
    Path.cwd().parent / "sample_sales.csv",
)


def _sample_file() -> Path | None:
    return next((p for p in _SAMPLE_CANDIDATES if p.is_file()), None)


def demo_login_id() -> str:
    return settings.demo_login.strip().lower()


def seed_demo(db: Session) -> None:
    """Create the demo user if absent and give it the sample dataset."""
    if not settings.demo_mode:
        return

    login = demo_login_id()
    user = db.query(User).filter(User.email == login).first()
    if user is None:
        user = User(
            id=new_user_id(),
            email=login,
            password_hash=hash_password(settings.demo_password),
        )
        db.add(user)
        db.commit()

    # Already has data -- either the sample from a previous boot, or something a
    # visitor uploaded. Either way, don't add a duplicate sample on every restart.
    if store.list_records(db, user.id):
        return

    sample = _sample_file()
    if sample is None:
        return
    store.create_dataset(db, user.id, sample.read_bytes(), sample.name)
