from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    datasets: Mapped[list["DatasetRecord"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class Blob(Base):
    """Uploaded file bytes, for STORAGE_BACKEND=db.

    Lets a deployment persist uploads with nothing but a database -- no object
    store, no persistent disk. `key` is the same opaque storage key the other
    backends use, so the three are interchangeable.
    """

    __tablename__ = "blobs"

    key: Mapped[str] = mapped_column(String(512), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class DatasetRecord(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(1024))  # opaque storage key: "<id>/<filename>"
    n_rows: Mapped[int] = mapped_column(Integer)
    n_cols: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    owner: Mapped[User] = relationship(back_populates="datasets")

    def summary(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "created_at": self.created_at.isoformat(),
            "n_rows": self.n_rows,
            "n_cols": self.n_cols,
        }
