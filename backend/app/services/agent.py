"""The ask loop: profile -> Gemini -> sandbox -> retry on error -> verify."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import pandas as pd

from app.config import settings
from app.services import telemetry, verify
from app.services.llm import critique_code, generate_code
from app.services.sandbox import run_code
from app.services.viz import suggest_chart

MAX_ATTEMPTS = 3


@dataclass
class Attempt:
    code: str
    ok: bool
    error: str | None = None


@dataclass
class AskResult:
    ok: bool
    question: str
    attempts: list[Attempt] = field(default_factory=list)
    code: str | None = None
    result: dict | None = None
    chart: dict | None = None
    error: str | None = None
    confidence: str | None = None       # "high" | "medium" | "low"
    checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "question": self.question,
            "code": self.code,
            "result": self.result,
            "chart": self.chart,
            "error": self.error,
            "confidence": self.confidence,
            "checks": self.checks,
            "attempts": [
                {"code": a.code, "ok": a.ok, "error": a.error} for a in self.attempts
            ],
            "n_attempts": len(self.attempts),
        }


def ask(df: pd.DataFrame, profile: dict, question: str,
        max_attempts: int = MAX_ATTEMPTS) -> AskResult:
    out = AskResult(ok=False, question=question)
    error: str | None = None

    for attempt in range(1, max_attempts + 1):
        telemetry.current_attempt.set(attempt)
        code = generate_code(profile, question, error)
        run = run_code(df, code)

        if run["ok"]:
            out.attempts.append(Attempt(code=code, ok=True))
            out.ok = True
            out.code = code
            out.result = run["result"]
            out.chart = suggest_chart(run["result"])
            _verify(out, profile, question)
            return out

        error = run["error"]
        out.attempts.append(Attempt(code=code, ok=False, error=error))

    out.error = error
    out.code = out.attempts[-1].code if out.attempts else None
    return out


def _verify(out: AskResult, profile: dict, question: str) -> None:
    """Attach a confidence level + human-readable notes to a successful result."""
    if not settings.verify_answers:
        return

    issues = verify.check_invariants(out.result, profile, question)

    verdict: str | None = None
    reason = ""
    try:
        verdict, reason = critique_code(
            profile, question, out.code, json.dumps(out.result, default=str)
        )
    except Exception:  # noqa: BLE001 - verification must never break an answer
        verdict = None

    out.confidence = verify.classify(issues, verdict)
    notes = [msg for _sev, msg in issues]
    if verdict == "FAIL":
        notes.append(f"Reviewer flagged the code: {reason}" if reason
                     else "A reviewer model flagged this code as not answering the question.")
    out.checks = notes
