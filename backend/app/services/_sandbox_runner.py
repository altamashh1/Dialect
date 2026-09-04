"""Runs INSIDE an isolated subprocess. Do not import from the app package here.

Usage: python -I _sandbox_runner.py <input_pickle> <output_json> <mem_mb> <out_mb>

input pickle: {"df": <DataFrame>, "code": <str>}
output json:  {"ok": bool, ...}

Layer 2 of the sandbox (see SECURITY.md): the generated code gets a globals dict
containing only a reduced `__builtins__`, a curated `pd` facade, and `df`. The
facade matters as much as the builtins -- real `pandas` exposes submodules, and
`pd.io.common.os` hands out the `os` module without touching a single dunder.
"""
import json
import math
import os
import pickle
import sys
import traceback

import pandas as pd

# `python -I` implies `-P`, so the script's own directory is not on sys.path and
# a plain sibling import would fail. This runs before any generated code.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _limits  # noqa: E402

MAX_RESULT_ROWS = 500

_BUILTIN_NAMES = (
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter",
    "float", "int", "len", "list", "map", "max", "min", "range", "reversed",
    "round", "set", "sorted", "str", "sum", "tuple", "zip", "print",
    "isinstance", "repr", "frozenset",
)
# Deliberately absent: getattr/hasattr (turn any string into an attribute
# access), type (walks the class hierarchy), and everything in
# code_guard.DENIED_NAMES.
SAFE_BUILTINS = {
    k: __builtins__[k] if isinstance(__builtins__, dict) else getattr(__builtins__, k)
    for k in _BUILTIN_NAMES
}

# Top-level pandas names the generated code may use. Anything not listed --
# every submodule included -- simply does not exist on the facade.
_PANDAS_EXPORTS = (
    "DataFrame", "Series", "Index", "MultiIndex", "Categorical",
    "CategoricalDtype", "Grouper", "NamedAgg", "IndexSlice", "DateOffset",
    "Period", "Timedelta", "Timestamp", "NA", "NaT",
    "concat", "merge", "merge_asof", "melt", "pivot", "pivot_table", "crosstab",
    "cut", "qcut", "get_dummies", "factorize", "unique", "array",
    "isna", "isnull", "notna", "notnull",
    "to_datetime", "to_numeric", "to_timedelta",
    "date_range", "bdate_range", "period_range", "timedelta_range",
)


class _PandasFacade:
    """A `pd` with only the analysis surface -- no submodules, no I/O."""

    def __getattr__(self, name):
        raise AttributeError(
            f"`pd.{name}` is not available in the sandbox. "
            "Only DataFrame/Series operations and common helpers are exposed."
        )


def _build_pandas_facade():
    facade = _PandasFacade()
    for name in _PANDAS_EXPORTS:
        value = getattr(pd, name, None)
        # Never re-expose a module: that is the `pd.io.common.os` escape route.
        if value is not None and not isinstance(value, type(pd)):
            object.__setattr__(facade, name, value)
    return facade


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if hasattr(v, "item"):
        try:
            return v.item()
        except (ValueError, TypeError):
            return str(v)
    return v


def _serialize(result):
    if isinstance(result, pd.DataFrame):
        capped = result.head(MAX_RESULT_ROWS)
        return {
            "kind": "dataframe",
            "shape": [int(result.shape[0]), int(result.shape[1])],
            "truncated": bool(result.shape[0] > MAX_RESULT_ROWS),
            "columns": [str(c) for c in capped.columns],
            "data": [
                {str(k): _clean(v) for k, v in row.items()}
                for row in capped.to_dict(orient="records")
            ],
        }
    if isinstance(result, pd.Series):
        capped = result.head(MAX_RESULT_ROWS)
        return {
            "kind": "series",
            "name": _clean(result.name),
            "length": int(result.shape[0]),
            "truncated": bool(result.shape[0] > MAX_RESULT_ROWS),
            "index": [_clean(i) for i in capped.index],
            "values": [_clean(v) for v in capped.values],
        }
    return {"kind": "scalar", "value": _clean(result)}


def main() -> int:
    in_path, out_path = sys.argv[1], sys.argv[2]
    memory_mb = int(sys.argv[3]) if len(sys.argv) > 3 else 512
    output_mb = int(sys.argv[4]) if len(sys.argv) > 4 else 8

    with open(in_path, "rb") as fh:
        payload = pickle.load(fh)
    df, code = payload["df"], payload["code"]

    # Everything above this line is trusted. Apply OS limits last, so the limits
    # are in force for the exec below and nothing untrusted has run yet.
    _limits.apply_limits(memory_mb, output_mb)

    sandbox_globals = {
        "__builtins__": SAFE_BUILTINS,
        "pd": _build_pandas_facade(),
        "df": df,
    }

    try:
        exec(compile(code, "<generated>", "exec"), sandbox_globals)
    except MemoryError:
        out = {"ok": False, "error": f"Code exceeded the {memory_mb}MB memory limit."}
    except BaseException:  # noqa: BLE001 - a crash must still produce output
        out = {"ok": False, "error": traceback.format_exc(limit=3)}
    else:
        if "result" not in sandbox_globals:
            out = {"ok": False, "error": "Code did not assign a `result` variable."}
        else:
            try:
                out = {"ok": True, "result": _serialize(sandbox_globals["result"])}
            except Exception:
                out = {"ok": False, "error": "Could not serialize result:\n"
                       + traceback.format_exc(limit=2)}

    body = json.dumps(out, default=str)
    if len(body) > output_mb * 1024 * 1024:
        body = json.dumps({
            "ok": False,
            "error": f"Result was larger than the {output_mb}MB output limit.",
        })

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
