"""Thin wrapper around the Google Gemini API for code generation."""
from __future__ import annotations

import time
from functools import lru_cache

from app.config import settings
from app.services import telemetry
from app.services.prompt import (
    CRITIC_SYSTEM_INSTRUCTION,
    SYSTEM_INSTRUCTION,
    build_critic_prompt,
    build_prompt,
    extract_code,
    parse_verdict,
)


class LLMError(RuntimeError):
    """Raised when the LLM call cannot be completed."""


@lru_cache(maxsize=1)
def _client():
    if not settings.gemini_api_key:
        raise LLMError("GEMINI_API_KEY is not set. Add it to backend/.env")
    from google import genai  # imported lazily so tests don't need the package configured

    return genai.Client(api_key=settings.gemini_api_key)


def generate_code(profile: dict, question: str, error: str | None = None) -> str:
    """Ask Gemini for pandas code answering `question` about the profiled data."""
    from google.genai import types

    prompt = build_prompt(profile, question, error)
    model = settings.gemini_model
    started = time.perf_counter()
    try:
        resp = _client().models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0,
            ),
        )
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001
        telemetry.record_call(model=model, started=started, ok=False, error=str(exc))
        raise LLMError(f"Gemini request failed: {exc}") from exc

    usage = getattr(resp, "usage_metadata", None)
    if not resp.text:
        telemetry.record_call(
            model=model, started=started, ok=False,
            usage=usage, error="empty response",
        )
        raise LLMError("Gemini returned an empty response.")

    telemetry.record_call(model=model, started=started, ok=True, usage=usage)
    return extract_code(resp.text)


def critique_code(
    profile: dict, question: str, code: str, result_repr: str
) -> tuple[str, str]:
    """Second-model review of generated code. Returns ('PASS'|'FAIL', reason).

    Never raises: on any failure it returns ('PASS', '') so verification is
    advisory and can't block an otherwise-good answer.
    """
    from google.genai import types

    model = settings.gemini_model
    started = time.perf_counter()
    try:
        resp = _client().models.generate_content(
            model=model,
            contents=build_critic_prompt(profile, question, code, result_repr),
            config=types.GenerateContentConfig(
                system_instruction=CRITIC_SYSTEM_INSTRUCTION,
                temperature=0,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        telemetry.record_call(
            model=model, started=started, ok=False, kind="critic", error=str(exc)
        )
        return "PASS", ""

    usage = getattr(resp, "usage_metadata", None)
    telemetry.record_call(
        model=model, started=started, ok=True, kind="critic", usage=usage
    )
    return parse_verdict(resp.text)
