"""Answer verification: deterministic invariant checks + an LLM critic pass.

The numbers themselves can't be hallucinated (pandas computes them), so the
failure mode we guard against is *correct code answering a subtly wrong
question*. Two independent signals:

1. check_invariants() - free, deterministic. Flags results that violate
   properties implied by the question or the schema (negative counts, a
   percentage outside 0-100, an empty result, null values in the output).
2. critique() - one LLM call. Asks a second model whether the generated code
   actually answers the question.

classify() folds both into confidence = high | medium | low.
"""
from __future__ import annotations

import math

_COUNT_WORDS = ("how many", "number of", "count of", "count the")
_PCT_WORDS = ("percent", "percentage", "%", "proportion", "share of", "ratio", "rate of")
_NONNEG_WORDS = ("revenue", "sales", "total", "sum", "count", "quantity", "amount",
                 "price", "cost", "spend", "profit")


def _numbers(result: dict):
    kind = result.get("kind")
    if kind == "scalar":
        v = result.get("value")
        return [v] if isinstance(v, (int, float)) and not isinstance(v, bool) else []
    if kind == "series":
        return [v for v in result.get("values", [])
                if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if kind == "dataframe":
        out = []
        for row in result.get("data", []):
            out += [v for v in row.values()
                    if isinstance(v, (int, float)) and not isinstance(v, bool)]
        return out
    return []


def _has_nulls(result: dict) -> bool:
    kind = result.get("kind")
    if kind == "scalar":
        return result.get("value") is None
    if kind == "series":
        return any(v is None for v in result.get("values", []))
    if kind == "dataframe":
        return any(v is None for row in result.get("data", []) for v in row.values())
    return False


def _is_empty(result: dict) -> bool:
    kind = result.get("kind")
    if kind == "series":
        return len(result.get("values", [])) == 0
    if kind == "dataframe":
        return len(result.get("data", [])) == 0
    return False


def check_invariants(result: dict, profile: dict, question: str) -> list[tuple[str, str]]:
    """Return a list of (severity, message); severity is 'error' or 'warn'."""
    q = question.lower()
    issues: list[tuple[str, str]] = []
    nums = _numbers(result)

    if any(isinstance(n, float) and (math.isnan(n) or math.isinf(n)) for n in nums):
        issues.append(("error", "Result contains a non-finite number (NaN/inf)."))

    if _is_empty(result):
        issues.append(("warn", "Result is empty — a filter may be too strict or a "
                               "column name wrong."))

    if _has_nulls(result):
        issues.append(("warn", "Result contains null values."))

    if any(w in q for w in _PCT_WORDS) and nums:
        if any(n < -0.001 or n > 100.001 for n in nums):
            issues.append(("error", "Question asks for a percentage but a value "
                                    "falls outside 0-100."))

    if any(w in q for w in _NONNEG_WORDS) and nums:
        if any(n < 0 for n in nums):
            issues.append(("warn", "Question implies a non-negative measure but the "
                                   "result contains negative values."))

    if any(q.strip().startswith(w) or w in q for w in _COUNT_WORDS):
        if result.get("kind") == "scalar":
            v = result.get("value")
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                if v < 0:
                    issues.append(("error", "A count came back negative."))
                elif isinstance(v, float) and not v.is_integer():
                    issues.append(("warn", "A 'how many' question returned a "
                                           "non-integer value."))
                n_rows = profile.get("n_rows")
                if isinstance(n_rows, int) and v > n_rows + 0.001:
                    issues.append(("warn", f"Count ({v:g}) exceeds the dataset row "
                                           f"count ({n_rows})."))

    return issues


def classify(issues: list[tuple[str, str]], critic_verdict: str | None) -> str:
    """Fold invariant issues + critic verdict into high | medium | low."""
    has_error = any(sev == "error" for sev, _ in issues)
    has_warn = any(sev == "warn" for sev, _ in issues)

    if has_error or critic_verdict == "FAIL":
        return "low"
    if has_warn or critic_verdict is None:
        return "medium"
    return "high"
