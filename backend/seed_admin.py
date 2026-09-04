r"""Create (or reset) a default login.

Usage:
    .\.venv\Scripts\python.exe seed_admin.py

Login id: Admin      (case-insensitive)
Password: admin8828
"""

from __future__ import annotations

from app.auth import hash_password, new_user_id
from app.db import SessionLocal, init_db
from app.models import User

LOGIN_ID = "admin"  # stored lowercase; the login form lowercases input
PASSWORD = "admin8828"


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == LOGIN_ID).first()
        if user is None:
            user = User(id=new_user_id(), email=LOGIN_ID, password_hash=hash_password(PASSWORD))
            db.add(user)
            action = "created"
        else:
            user.password_hash = hash_password(PASSWORD)
            action = "password reset"
        db.commit()
        print(f"Default login {action}:  id='Admin'  password='{PASSWORD}'")
    finally:
        db.close()


if __name__ == "__main__":
    main()
