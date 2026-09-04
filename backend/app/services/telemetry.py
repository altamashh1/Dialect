"""In-process observability for LLM calls.

Every call to Gemini is recorded here: model, latency, token counts, an
estimated dollar cost, which retry attempt it was, and whether it succeeded.
The data feeds the `/api/stats` endpoint and is also emitted as one structured
JSON log line per call (logger name ``llm.telemetry``).

This is deliberately in-process (a ring buffer + running aggregates), matching
the caching brick: same trade-off, same swap-for-Redis/OTel story later.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

log = logging.getLogger("llm.telemetry")

# USD per 1M tokens (input, output). Public list prices change often and vary by
# tier, so treat these as estimates; override via set_pricing() in production.
_PRICING: dict[str, tuple[float, float]] = {
    "gemini-3.5-flash-lite": (0.10, 0.40),
    "gemini-3.6-flash": (0.30, 2.50),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
}
_DEFAULT_PRICE = (0.10, 0.40)

MAX_EVENTS = 500

# Set by the agent loop before each generate_code() call so the recorder knows
# which attempt this is without threading a parameter through the call chain.
current_attempt: ContextVar[int] = ContextVar("current_attempt", default=1)


def set_pricing(model: str, input_per_mtok: float, output_per_mtok: float) -> None:
    _PRICING[model] = (input_per_mtok, output_per_mtok)


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_price, out_price = _PRICING.get(model, _DEFAULT_PRICE)
    return round(
        prompt_tokens / 1_000_000 * in_price
        + completion_tokens / 1_000_000 * out_price,
        6,
    )


@dataclass
class LLMCall:
    ts: float
    model: str
    latency_ms: float
    attempt: int
    is_retry: bool
    ok: bool
    kind: str = "generate"  # "generate" | "critic"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None

    @property
    def iso(self) -> str:
        return datetime.fromtimestamp(self.ts, tz=timezone.utc).isoformat()


@dataclass
class _Aggregates:
    calls: int = 0
    ok: int = 0
    failed: int = 0
    retries: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    by_model: dict[str, dict] = field(default_factory=dict)


class Recorder:
    def __init__(self, max_events: int = MAX_EVENTS) -> None:
        self._lock = threading.Lock()
        self._events: deque[LLMCall] = deque(maxlen=max_events)
        self._agg = _Aggregates()
        self._started = time.time()

    def record(self, call: LLMCall) -> None:
        with self._lock:
            self._events.append(call)
            a = self._agg
            a.calls += 1
            a.ok += int(call.ok)
            a.failed += int(not call.ok)
            a.retries += int(call.is_retry)
            a.prompt_tokens += call.prompt_tokens
            a.completion_tokens += call.completion_tokens
            a.total_tokens += call.total_tokens
            a.cost_usd = round(a.cost_usd + call.cost_usd, 6)
            m = a.by_model.setdefault(
                call.model, {"calls": 0, "ok": 0, "total_tokens": 0, "cost_usd": 0.0}
            )
            m["calls"] += 1
            m["ok"] += int(call.ok)
            m["total_tokens"] += call.total_tokens
            m["cost_usd"] = round(m["cost_usd"] + call.cost_usd, 6)

        log.info(
            json.dumps(
                {
                    "event": "llm_call",
                    "ts": call.iso,
                    "model": call.model,
                    "kind": call.kind,
                    "latency_ms": round(call.latency_ms, 1),
                    "attempt": call.attempt,
                    "is_retry": call.is_retry,
                    "ok": call.ok,
                    "prompt_tokens": call.prompt_tokens,
                    "completion_tokens": call.completion_tokens,
                    "cost_usd": call.cost_usd,
                    "error": call.error,
                }
            )
        )

    def stats(self) -> dict:
        with self._lock:
            events = list(self._events)
            a = self._agg
            latencies = sorted(e.latency_ms for e in events)
            recent_errors = [
                {"ts": e.iso, "model": e.model, "error": e.error}
                for e in reversed(events)
                if not e.ok
            ][:10]
            recent_calls = [
                {
                    "ts": e.iso,
                    "model": e.model,
                    "kind": e.kind,
                    "latency_ms": round(e.latency_ms, 1),
                    "attempt": e.attempt,
                    "ok": e.ok,
                    "total_tokens": e.total_tokens,
                    "cost_usd": e.cost_usd,
                }
                for e in list(reversed(events))[:20]
            ]
            return {
                "since": datetime.fromtimestamp(
                    self._started, tz=timezone.utc
                ).isoformat(),
                "llm_calls": {
                    "total": a.calls,
                    "ok": a.ok,
                    "failed": a.failed,
                    "success_rate": round(a.ok / a.calls, 4) if a.calls else None,
                    "retries": a.retries,
                    "latency_ms": {
                        "p50": _pct(latencies, 50),
                        "p95": _pct(latencies, 95),
                        "max": round(latencies[-1], 1) if latencies else None,
                    },
                    "tokens": {
                        "prompt": a.prompt_tokens,
                        "completion": a.completion_tokens,
                        "total": a.total_tokens,
                    },
                    "est_cost_usd": round(a.cost_usd, 6),
                    "by_model": a.by_model,
                    "window_events": len(events),
                },
                "recent_errors": recent_errors,
                "recent_calls": recent_calls,
            }

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._agg = _Aggregates()
            self._started = time.time()


def _pct(sorted_values: list[float], p: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return round(sorted_values[0], 1)
    rank = (p / 100) * (len(sorted_values) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = rank - lo
    return round(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac, 1)


recorder = Recorder()


def record_call(
    *,
    model: str,
    started: float,
    ok: bool,
    kind: str = "generate",
    usage: object | None = None,
    error: str | None = None,
) -> None:
    """Build an LLMCall from a Gemini response's usage metadata and record it."""
    prompt_tokens = _getattr_int(usage, "prompt_token_count")
    completion_tokens = _getattr_int(usage, "candidates_token_count")
    total_tokens = _getattr_int(usage, "total_token_count") or (
        prompt_tokens + completion_tokens
    )
    attempt = current_attempt.get() if kind == "generate" else 1
    recorder.record(
        LLMCall(
            ts=time.time(),
            model=model,
            latency_ms=(time.perf_counter() - started) * 1000,
            attempt=attempt,
            is_retry=attempt > 1,
            ok=ok,
            kind=kind,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=estimate_cost(model, prompt_tokens, completion_tokens),
            error=error,
        )
    )


def _getattr_int(obj: object | None, name: str) -> int:
    try:
        return int(getattr(obj, name, 0) or 0)
    except (TypeError, ValueError):
        return 0
