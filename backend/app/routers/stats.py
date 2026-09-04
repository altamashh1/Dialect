"""Operational stats: how the LLM pipeline is behaving in this process."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.config import settings
from app.models import User
from app.services.cache import answer_cache
from app.services.telemetry import recorder

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def get_stats(_: User = Depends(get_current_user)) -> dict:
    data = recorder.stats()
    data["model"] = settings.gemini_model
    data["answer_cache_size"] = len(answer_cache)
    return data
