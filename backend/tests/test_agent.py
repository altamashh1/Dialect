import pandas as pd
import pytest

from app.config import settings
from app.services import agent


@pytest.fixture
def df():
    return pd.DataFrame({"age": [30, 25, 40], "city": ["NYC", "LA", "SF"]})


PROFILE = {"n_rows": 3, "columns": {}}


def test_succeeds_first_try(df, monkeypatch):
    monkeypatch.setattr(agent, "generate_code", lambda *a, **k: "result = df['age'].max()")
    out = agent.ask(df, PROFILE, "max age?")
    assert out.ok
    assert out.result["value"] == 40
    assert len(out.attempts) == 1


def test_retries_then_succeeds(df, monkeypatch):
    codes = iter(["result = df['Age'].max()", "result = df['age'].max()"])
    seen_errors = []

    def fake_gen(profile, question, error=None):
        seen_errors.append(error)
        return next(codes)

    monkeypatch.setattr(agent, "generate_code", fake_gen)
    out = agent.ask(df, PROFILE, "max age?")

    assert out.ok
    assert len(out.attempts) == 2
    assert seen_errors[0] is None
    assert "KeyError" in seen_errors[1]


def test_verify_sets_confidence_high_on_clean_pass(df, monkeypatch):
    monkeypatch.setattr(settings, "verify_answers", True)
    monkeypatch.setattr(agent, "generate_code", lambda *a, **k: "result = df['age'].max()")
    monkeypatch.setattr(agent, "critique_code", lambda *a, **k: ("PASS", ""))

    out = agent.ask(df, {"n_rows": 3, "columns": {}}, "max age?")
    assert out.confidence == "high"
    assert out.checks == []


def test_verify_low_confidence_when_critic_fails(df, monkeypatch):
    monkeypatch.setattr(settings, "verify_answers", True)
    monkeypatch.setattr(agent, "generate_code", lambda *a, **k: "result = df['age'].mean()")
    monkeypatch.setattr(
        agent, "critique_code", lambda *a, **k: ("FAIL", "used mean, question wants max")
    )

    out = agent.ask(df, {"n_rows": 3, "columns": {}}, "max age?")
    assert out.confidence == "low"
    assert any("mean" in c for c in out.checks)
    assert out.to_dict()["confidence"] == "low"


def test_verify_medium_when_critic_unavailable(df, monkeypatch):
    monkeypatch.setattr(settings, "verify_answers", True)
    monkeypatch.setattr(agent, "generate_code", lambda *a, **k: "result = df['age'].max()")

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(agent, "critique_code", boom)
    out = agent.ask(df, {"n_rows": 3, "columns": {}}, "max age?")
    assert out.confidence == "medium"


def test_gives_up_after_max_attempts(df, monkeypatch):
    monkeypatch.setattr(agent, "generate_code", lambda *a, **k: "result = df['bad'].max()")
    out = agent.ask(df, PROFILE, "max age?", max_attempts=2)

    assert not out.ok
    assert len(out.attempts) == 2
    assert "KeyError" in out.error
    d = out.to_dict()
    assert d["n_attempts"] == 2
    assert d["code"] is not None
