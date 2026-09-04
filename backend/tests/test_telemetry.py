import time

from app.services import telemetry
from app.services.telemetry import LLMCall, Recorder, estimate_cost


def _call(**kw):
    base = dict(
        ts=time.time(), model="gemini-3.5-flash-lite", latency_ms=100.0,
        attempt=1, is_retry=False, ok=True,
        prompt_tokens=1000, completion_tokens=200, total_tokens=1200,
        cost_usd=estimate_cost("gemini-3.5-flash-lite", 1000, 200),
    )
    base.update(kw)
    return LLMCall(**base)


def test_cost_estimate():
    # 1M input @ $0.10 + 1M output @ $0.40
    assert estimate_cost("gemini-3.5-flash-lite", 1_000_000, 0) == 0.10
    assert estimate_cost("gemini-3.5-flash-lite", 0, 1_000_000) == 0.40
    assert estimate_cost("unknown-model", 1_000_000, 0) == 0.10  # default price


def test_aggregates_and_success_rate():
    r = Recorder()
    r.record(_call(ok=True))
    r.record(_call(ok=True))
    r.record(_call(ok=False, error="boom", attempt=2, is_retry=True))

    s = r.stats()["llm_calls"]
    assert s["total"] == 3
    assert s["ok"] == 2
    assert s["failed"] == 1
    assert s["retries"] == 1
    assert s["success_rate"] == round(2 / 3, 4)
    assert s["tokens"]["total"] == 3600
    assert s["by_model"]["gemini-3.5-flash-lite"]["calls"] == 3


def test_latency_percentiles():
    r = Recorder()
    for ms in [10, 20, 30, 40, 100]:
        r.record(_call(latency_ms=float(ms)))
    lat = r.stats()["llm_calls"]["latency_ms"]
    assert lat["p50"] == 30.0
    assert lat["max"] == 100.0
    assert lat["p95"] >= 40.0


def test_recent_errors_capped_and_newest_first():
    r = Recorder()
    r.record(_call(ok=False, error="first"))
    r.record(_call(ok=True))
    r.record(_call(ok=False, error="second"))
    errors = r.stats()["recent_errors"]
    assert [e["error"] for e in errors] == ["second", "first"]


def test_ring_buffer_bounds_memory():
    r = Recorder(max_events=5)
    for _ in range(20):
        r.record(_call())
    assert r.stats()["llm_calls"]["window_events"] == 5
    # aggregates still count every call ever seen
    assert r.stats()["llm_calls"]["total"] == 20


def test_attempt_contextvar_marks_retries(monkeypatch):
    r = Recorder()
    monkeypatch.setattr(telemetry, "recorder", r)
    telemetry.current_attempt.set(2)
    telemetry.record_call(model="m", started=time.perf_counter(), ok=True)
    telemetry.current_attempt.set(1)
    call = r.stats()["recent_calls"][0]
    assert call["attempt"] == 2
