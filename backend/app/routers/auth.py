from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import (
    create_token,
    get_current_user,
    hash_password,
    new_user_id,
    verify_password,
)
from app.config import settings
from app.db import get_db
from app.models import User
from app.services.demo import demo_login_id

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Credentials(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    token: str
    email: str


@router.post("/signup", response_model=TokenResponse)
def signup(body: Credentials, db: Session = Depends(get_db)) -> TokenResponse:
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(422, "Invalid email address.")
    if len(body.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters.")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "An account with that email already exists.")

    user = User(id=new_user_id(), email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return TokenResponse(token=create_token(user.id), email=email)


@router.post("/login", response_model=TokenResponse)
def login(body: Credentials, db: Session = Depends(get_db)) -> TokenResponse:
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password.")
    return TokenResponse(token=create_token(user.id), email=user.email)


@router.post("/demo", response_model=TokenResponse)
def demo_signin(db: Session = Depends(get_db)) -> TokenResponse:
    """One-click sign-in to the shared demo account.

    Takes no credentials on purpose: the demo password would otherwise have to
    ship in the frontend bundle. Returns 404 unless DEMO_MODE is on, so a
    production deployment without a demo exposes no extra surface.
    """
    if not settings.demo_mode:
        raise HTTPException(404, "Demo access is not enabled.")

    user = db.query(User).filter(User.email == demo_login_id()).first()
    if user is None:
        raise HTTPException(503, "The demo account is still being prepared.")
    return TokenResponse(token=create_token(user.id), email=user.email)


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return {"id": user.id, "email": user.email}
