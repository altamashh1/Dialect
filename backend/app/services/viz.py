"""Pick a chart spec from a sandbox result. Pure heuristics, no LLM call.

Output spec consumed by the React <Chart> component:
  {"chart": "scalar"|"table"|"bar"|"line"|"scatter",
   "x": <key|None>, "y": <key|None>,
   "data": [ {..}, .. ],
   "reason": <str>}
"""
from __future__ import annotations

from datetime import date, datetime

MAX_CATEGORIES = 50

_NUMERIC = (int, float)


def _is_number(v) -> bool:
    return isinstance(v, _NUMERIC) and not isinstance(v, bool)


def _looks_temporal(v) -> bool:
    if isinstance(v, (datetime, date)):
        return True
    if isinstance(v, str) and len(v) >= 6:
        head = v[:10]
        return head[:4].isdigit() and ("-" in head or "/" in head)
    return False


def suggest_chart(result: dict) -> dict:
    kind = result.get("kind")
    if kind == "scalar":
        return {"chart": "scalar", "x": None, "y": None,
                "data": [{"value": result.get("value")}],
                "reason": "Single value."}
    if kind == "series":
        return _from_series(result)
    if kind == "dataframe":
        return _from_dataframe(result)
    return _table([], "Unrecognized result.")


def _table(data, reason) -> dict:
    return {"chart": "table", "x": None, "y": None, "data": data, "reason": reason}


def _from_series(result: dict) -> dict:
    idx = result.get("index", [])
    vals = result.get("values", [])
    data = [{"name": _label(i), "value": v} for i, v in zip(idx, vals)]

    if not data or not all(_is_number(d["value"]) for d in data):
        return _table(data, "Series is non-numeric.")
    if len(data) > MAX_CATEGORIES:
        return _table(data, f"Too many points ({len(data)}) to chart.")

    if all(_looks_temporal(i) for i in idx):
        return {"chart": "line", "x": "name", "y": "value", "data": data,
                "reason": "Numeric values over a time index."}
    return {"chart": "bar", "x": "name", "y": "value", "data": data,
            "reason": "Numeric values across categories."}


def _from_dataframe(result: dict) -> dict:
    cols = result.get("columns", [])
    rows = result.get("data", [])

    if not rows:
        return _table(rows, "Empty result.")
    if len(rows) == 1 or len(cols) == 1:
        return _table(rows, "Single row/column — better as a table.")
    if len(cols) != 2:
        return _table(rows, f"{len(cols)} columns — showing as a table.")
    if len(rows) > MAX_CATEGORIES:
        return _table(rows, f"{len(rows)} rows — showing as a table.")

    xcol, ycol = cols
    xs = [r.get(xcol) for r in rows]
    ys = [r.get(ycol) for r in rows]

    if not all(_is_number(y) for y in ys):
        return _table(rows, f"'{ycol}' is not numeric.")

    if all(_looks_temporal(x) for x in xs):
        return {"chart": "line", "x": xcol, "y": ycol, "data": rows,
                "reason": f"'{ycol}' over time ('{xcol}')."}
    if all(_is_number(x) for x in xs):
        return {"chart": "scatter", "x": xcol, "y": ycol, "data": rows,
                "reason": f"Two numeric columns — '{xcol}' vs '{ycol}'."}
    return {"chart": "bar", "x": xcol, "y": ycol, "data": rows,
            "reason": f"'{ycol}' by '{xcol}'."}


def _label(v) -> str:
    return v if isinstance(v, str) else str(v)
