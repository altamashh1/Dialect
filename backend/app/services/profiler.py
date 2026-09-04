"""Build a compact schema profile of a DataFrame for LLM context and the UI."""
from __future__ import annotations

import math
from typing import Any

import pandas as pd
from pandas.api import types as ptypes

SAMPLE_ROWS = 5
SAMPLE_VALUES = 5


def _clean(value: Any) -> Any:
    """Make a value JSON-safe (no NaN / numpy scalars / Timestamps)."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalar
        try:
            return value.item()
        except (ValueError, TypeError):
            return str(value)
    return value


def _logical_type(series: pd.Series) -> str:
    if ptypes.is_bool_dtype(series):
        return "boolean"
    if ptypes.is_integer_dtype(series):
        return "integer"
    if ptypes.is_float_dtype(series):
        return "float"
    if ptypes.is_datetime64_any_dtype(series):
        return "datetime"
    if isinstance(series.dtype, pd.CategoricalDtype):
        return "categorical"
    return "string"


def _column_profile(series: pd.Series) -> dict:
    n = len(series)
    non_null = series.dropna()
    n_null = int(series.isna().sum())
    ltype = _logical_type(series)

    col: dict[str, Any] = {
        "dtype": str(series.dtype),
        "type": ltype,
        "null_count": n_null,
        "null_pct": round(100 * n_null / n, 2) if n else 0.0,
        "unique_count": int(non_null.nunique()),
    }

    if ltype in {"integer", "float"} and not non_null.empty:
        col["min"] = _clean(non_null.min())
        col["max"] = _clean(non_null.max())
        col["mean"] = _clean(round(float(non_null.mean()), 4))
    elif ltype == "datetime" and not non_null.empty:
        col["min"] = _clean(non_null.min())
        col["max"] = _clean(non_null.max())

    col["sample_values"] = [_clean(v) for v in non_null.unique()[:SAMPLE_VALUES]]
    return col


def profile_dataframe(df: pd.DataFrame) -> dict:
    columns = {name: _column_profile(df[name]) for name in df.columns}
    sample_rows = [
        {k: _clean(v) for k, v in row.items()}
        for row in df.head(SAMPLE_ROWS).to_dict(orient="records")
    ]
    return {
        "n_rows": int(df.shape[0]),
        "n_cols": int(df.shape[1]),
        "columns": columns,
        "sample_rows": sample_rows,
    }
