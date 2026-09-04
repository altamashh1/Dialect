"""Execute LLM-generated pandas code in an isolated subprocess.

Three layers, none of which is sufficient alone (see SECURITY.md):

1. `code_guard.validate` -- AST rules reject imports, private/dunder attribute
   hops, introspection builtins, and pandas file I/O before anything runs.
2. `_sandbox_runner.py` -- a separate `python -I` process whose globals hold only
   reduced builtins, a curated `pd` facade, and a pickled copy of `df`.
3. `_limits.py` -- OS resource limits (rlimits on POSIX, a Job Object on
   Windows) plus a hard wall-clock timeout enforced here.

The child is also handed a scrubbed environment (`_child_env`), so a future hole
in layers 1 and 2 leaks an empty room rather than the API's secrets.

The honest limit: layers 1 and 2 are in-process Python restrictions, and
CPython's object graph is not designed to be a security boundary. Untrusted
multi-tenant input needs layer 3 to be a container, not just rlimits.
"""
from __future__ import annotations

import json
import os
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from app.config import settings
from app.services import code_guard

_RUNNER = Path(__file__).with_name("_sandbox_runner.py")

# The only environment variables the child is given. Everything else the API
# process holds -- GEMINI_API_KEY, JWT_SECRET, AWS_SECRET_ACCESS_KEY,
# DATABASE_URL -- is dropped, so reaching `os.environ` inside the sandbox is
# worth nothing. Layers 1 and 2 are denylists over a language that keeps
# growing new ways to spell "getattr"; this bounds what the next miss costs.
_ENV_ALLOWLIST = (
    "PATH",           # Python and numpy load their DLLs/.so files through it
    "SystemRoot", "SYSTEMROOT", "windir", "WINDIR", "COMSPEC", "PATHEXT",
    "TEMP", "TMP", "TMPDIR",
    "HOME",           # numpy/pandas probe it for config on POSIX
    "LANG", "LC_ALL", "LC_CTYPE",
    "NUMBER_OF_PROCESSORS",
)


def _child_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
    # Keep the child from writing .pyc files into the app directory, and make
    # its stdout encoding deterministic for the traceback we surface on error.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_code(df: pd.DataFrame, code: str, timeout: int | None = None) -> dict:
    """Return {"ok": True, "result": {...}} or {"ok": False, "error": str}."""
    timeout = timeout or settings.sandbox_timeout_seconds
    memory_mb = settings.sandbox_memory_mb
    output_mb = settings.sandbox_output_mb

    rejection = code_guard.check(code)
    if rejection is not None:
        return {"ok": False, "error": rejection}

    with tempfile.TemporaryDirectory() as tmp:
        in_path = Path(tmp) / "in.pkl"
        out_path = Path(tmp) / "out.json"
        with in_path.open("wb") as fh:
            pickle.dump({"df": df, "code": code}, fh)

        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(_RUNNER), str(in_path), str(out_path),
                 str(memory_mb), str(output_mb)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmp,
                env=_child_env(),
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"Execution timed out after {timeout}s."}

        if not out_path.exists():
            stderr = (proc.stderr or "").strip() or "sandbox produced no output"
            return {"ok": False, "error": f"Sandbox crashed:\n{stderr[:2000]}"}

        # The runner caps its own output, but it is untrusted-adjacent: never
        # read an unbounded file into the API process.
        limit = output_mb * 1024 * 1024
        if out_path.stat().st_size > limit:
            return {"ok": False,
                    "error": f"Result was larger than the {output_mb}MB output limit."}

        try:
            return json.loads(out_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"ok": False, "error": "Sandbox produced unreadable output."}
