import pandas as pd
import pytest

from app.config import settings
from app.services import sandbox as sandbox_module
from app.services.sandbox import _child_env, run_code


@pytest.fixture
def df():
    return pd.DataFrame(
        {"age": [30, 25, 40, 35], "city": ["NYC", "LA", "SF", "LA"]}
    )


def test_scalar_result(df):
    out = run_code(df, "result = df['age'].mean()")
    assert out["ok"] is True
    assert out["result"]["kind"] == "scalar"
    assert out["result"]["value"] == 32.5


def test_dataframe_result(df):
    out = run_code(df, "result = df.groupby('city').size().reset_index(name='n')")
    assert out["ok"] is True
    assert out["result"]["kind"] == "dataframe"
    assert {"city", "n"} == set(out["result"]["columns"])


def test_series_result(df):
    out = run_code(df, "result = df['city'].value_counts()")
    assert out["ok"] is True
    assert out["result"]["kind"] == "series"


def test_missing_result_variable(df):
    out = run_code(df, "x = df['age'].sum()")
    assert out["ok"] is False
    assert "result" in out["error"]


def test_runtime_error_is_captured(df):
    out = run_code(df, "result = df['nope'].mean()")
    assert out["ok"] is False
    assert "KeyError" in out["error"]


def test_import_is_blocked(df):
    out = run_code(df, "import os\nresult = os.listdir('.')")
    assert out["ok"] is False
    assert "imports are not allowed" in out["error"]


def test_open_is_blocked(df):
    out = run_code(df, "result = open('secret.txt').read()")
    assert out["ok"] is False


def test_timeout(df):
    out = run_code(df, "result = sum(range(10**12))", timeout=2)
    assert out["ok"] is False
    assert "timed out" in out["error"]


# --- Runtime isolation (layers 2 and 3) -------------------------------------
# The AST guard is tested in test_code_guard.py. These check what survives if a
# trick gets past it, so they deliberately use code the guard does NOT reject.


def test_pandas_facade_hides_submodules(df):
    """`pd.io.common.os` is a module hop to `os` that uses no dunder at all."""
    out = run_code(df, "result = str(pd.io.common.os.getcwd())")
    assert out["ok"] is False
    assert "not available in the sandbox" in out["error"]


def test_pandas_facade_still_exposes_analysis_helpers(df):
    out = run_code(df, "result = pd.concat([df, df]).shape[0]")
    assert out["ok"] is True
    assert out["result"]["value"] == 8


def test_builtins_are_reduced(df):
    """A builtin layer 1 permits is still absent from the runtime namespace.

    `bytearray` is not on the AST denylist, so this reaches the subprocess and
    tests the reduced `__builtins__` rather than the guard in front of it.
    """
    out = run_code(df, "result = bytearray(8)")
    assert out["ok"] is False
    assert "not defined" in out["error"]


def test_memory_limit_is_enforced(df):
    out = run_code(df, "result = len('x' * (2000 * 1024 * 1024))", timeout=60)
    assert out["ok"] is False
    assert "memory limit" in out["error"]


def test_oversized_result_is_capped(df):
    out = run_code(
        df,
        "result = pd.DataFrame({'a': range(400), 'b': ['y' * 80000] * 400})",
        timeout=60,
    )
    assert out["ok"] is False
    assert "output limit" in out["error"]


def test_limits_refuse_to_run_outside_the_sandbox_process():
    """Applying these to the API process would stop it spawning sandboxes."""
    from app.services import _limits

    with pytest.raises(RuntimeError, match="_sandbox_runner.py"):
        _limits.apply_limits(512, 8)


def test_memory_cap_sized_for_real_use_does_not_break_ordinary_queries(df, monkeypatch):
    """A cap near actual RSS must not kill a trivial query.

    The POSIX limit is RLIMIT_DATA precisely because of this: RLIMIT_AS bounds
    virtual address space, which pandas and numpy over-reserve, so a cap this
    size would succeed at setrlimit() and then fail the first allocation after
    it -- turning every question in production into a spurious MemoryError.
    """
    monkeypatch.setattr(settings, "sandbox_memory_mb", 256)
    out = run_code(df, "result = df['age'].mean()", timeout=60)
    assert out["ok"] is True, out.get("error")
    assert out["result"]["value"] == 32.5


# --- The sandbox child's environment ----------------------------------------


def test_child_env_carries_no_secrets(monkeypatch):
    for name in ("GEMINI_API_KEY", "JWT_SECRET", "AWS_SECRET_ACCESS_KEY",
                 "DATABASE_URL", "S3_BUCKET"):
        monkeypatch.setenv(name, f"secret-value-for-{name}")

    env = _child_env()

    assert not any(v.startswith("secret-value-for-") for v in env.values())
    assert "PATH" in env  # ...without stripping what the interpreter needs


def test_reaching_os_environ_leaks_nothing_even_if_the_guard_is_bypassed(df, monkeypatch):
    """Layers 1 and 2 are denylists; this bounds what the next miss costs.

    The AST guard is disabled on purpose so the escape actually executes, which
    is the whole point: the child is handed an allowlisted environment, so a
    successful traversal to `os.environ` returns a room with nothing in it.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "secret-value-for-GEMINI_API_KEY")
    monkeypatch.setenv("JWT_SECRET", "secret-value-for-JWT_SECRET")
    monkeypatch.setattr(sandbox_module.code_guard, "check", lambda code: None)

    out = run_code(
        df,
        'result = "{0.__class__.__init__.__globals__[sys].modules[os].environ}"'
        ".format(df)",
        timeout=60,
    )

    assert out["ok"] is True, out.get("error")  # the escape itself still works
    assert "secret-value-for-" not in out["result"]["value"]
