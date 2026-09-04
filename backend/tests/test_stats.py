import time

from app.services.telemetry import LLMCall, recorder


def test_stats_requires_auth(client):
    assert client.get("/api/stats").status_code == 401


def test_stats_shape_and_live_data(auth_client):
    recorder.record(
        LLMCall(
            ts=time.time(), model="gemini-3.5-flash-lite", latency_ms=123.0,
            attempt=1, is_retry=False, ok=True,
            prompt_tokens=800, completion_tokens=120, total_tokens=920,
            cost_usd=0.000128,
        )
    )
    body = auth_client.get("/api/stats").json()

    assert body["model"] == "gemini-3.5-flash-lite"
    assert "answer_cache_size" in body
    assert body["llm_calls"]["total"] == 1
    assert body["llm_calls"]["tokens"]["total"] == 920
    assert body["llm_calls"]["est_cost_usd"] == 0.000128
    assert body["recent_calls"][0]["latency_ms"] == 123.0
