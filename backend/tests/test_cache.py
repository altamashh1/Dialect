import io

import pytest

from app.routers import datasets as router
from app.services.agent import AskResult, Attempt
from app.services.cache import TTLCache, answer_cache, make_key, normalize_question


def test_normalize_and_key_stability():
    assert normalize_question("  Average   AGE ? ") == "average age ?"
    assert make_key("d1", "Average age?") == make_key("d1", "  average   age? ")
    assert make_key("d1", "q") != make_key("d2", "q")


def test_ttl_expiry(monkeypatch):
    c = TTLCache(ttl_seconds=100)
    now = [1000.0]
    monkeypatch.setattr("app.services.cache.time.monotonic", lambda: now[0])
    c.set("k", "v")
    assert c.get("k") == "v"
    now[0] += 101
    assert c.get("k") is None


def test_lru_eviction():
    c = TTLCache(max_entries=2)
    c.set("a", 1)
    c.set("b", 2)
    c.get("a")
    c.set("c", 3)
    assert c.get("b") is None
    assert c.get("a") == 1
    assert c.get("c") == 3


def _ok_result(question):
    r = AskResult(ok=True, question=question)
    r.attempts.append(Attempt(code="result = 1", ok=True))
    r.code = "result = 1"
    r.result = {"kind": "scalar", "value": 1}
    r.chart = {"chart": "scalar", "data": [{"value": 1}]}
    return r


@pytest.fixture()
def dataset_id(auth_client):
    csv = b"age,city\n30,NYC\n25,LA\n"
    return auth_client.post(
        "/api/datasets", files={"file": ("d.csv", io.BytesIO(csv), "text/csv")}
    ).json()["id"]


def test_second_identical_question_is_cached(auth_client, dataset_id, monkeypatch):
    calls = []
    monkeypatch.setattr(
        router, "ask", lambda *a, **k: (calls.append(1), _ok_result("q"))[1]
    )

    r1 = auth_client.post(
        f"/api/datasets/{dataset_id}/ask", json={"question": "how many rows?"}
    )
    r2 = auth_client.post(
        f"/api/datasets/{dataset_id}/ask", json={"question": "How many   rows?"}
    )
    assert r1.json()["cached"] is False
    assert r2.json()["cached"] is True
    assert len(calls) == 1

    r3 = auth_client.post(
        f"/api/datasets/{dataset_id}/ask",
        json={"question": "how many rows?", "fresh": True},
    )
    assert r3.json()["cached"] is False
    assert len(calls) == 2


def test_failed_answer_not_cached(auth_client, dataset_id, monkeypatch):
    def fake(*a, **k):
        r = AskResult(ok=False, question="q")
        r.error = "boom"
        return r

    monkeypatch.setattr(router, "ask", fake)
    auth_client.post(f"/api/datasets/{dataset_id}/ask", json={"question": "q"})
    assert answer_cache.get(make_key(dataset_id, "q")) is None
