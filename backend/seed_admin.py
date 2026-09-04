r"""Create (or reset) the admin login.

The password is read from the ADMIN_PASSWORD environment variable (or the
`.env` file) and is never stored in this repository -- an earlier version of
this script hard-coded one, which meant anyone reading the public repo held the
credentials to any deployment that ran it.

Usage:
    # PowerShell
    $env:ADMIN_PASSWORD = "a-long-random-password"; .\.venv\Scripts\python.exe seed_admin.py

    # bash
    ADMIN_PASSWORD="a-long-random-password" python seed_admin.py

On Render, set ADMIN_PASSWORD in the service's environment and run this from
the Shell tab.

Login id: admin  (case-insensitive)
"""

from __future__ import annotations

import sys

from app.auth import hash_password, new_user_id
from app.config import settings
from app.db import SessionLocal, init_db
from app.models import User

LOGIN_ID = "admin"  # stored lowercase; the login form lowercases input
MIN_PASSWORD_CHARS = 12


def main() -> int:
    password = settings.admin_password
    if not password:
        print(
            "ADMIN_PASSWORD is not set.\n"
            "Refusing to seed an admin account with a default password -- this "
            "script and this repository are public.\n"
            'Set it first, e.g.  $env:ADMIN_PASSWORD = "..."  (PowerShell)',
            file=sys.stderr,
        )
        return 1

    if len(password) < MIN_PASSWORD_CHARS:
        print(
            f"ADMIN_PASSWORD is shorter than {MIN_PASSWORD_CHARS} characters. "
            "This account has admin access to every deployment it is created "
            "on; use something long.",
            file=sys.stderr,
        )
        return 1

    init_db()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == LOGIN_ID).first()
        if user is None:
            user = User(
                id=new_user_id(),
                email=LOGIN_ID,
                password_hash=hash_password(password),
            )
            db.add(user)
            action = "created"
        else:
            user.password_hash = hash_password(password)
            action = "password reset"
        db.commit()
        print(f"Admin login {action}:  id='admin'  password=<ADMIN_PASSWORD>")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
