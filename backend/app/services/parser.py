"""Load an uploaded file into a pandas DataFrame."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd

SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".json"}


class ParseError(ValueError):
    """Raised when a file cannot be parsed into a tabular DataFrame."""


def parse_bytes(raw: bytes, filename: str) -> pd.DataFrame:
    """Parse raw file bytes into a DataFrame based on the file extension."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ParseError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    try:
        if ext == ".csv":
            df = pd.read_csv(io.BytesIO(raw))
        elif ext == ".tsv":
            df = pd.read_csv(io.BytesIO(raw), sep="\t")
        elif ext in {".xlsx", ".xls"}:
            df = pd.read_excel(io.BytesIO(raw))
        elif ext == ".json":
            df = _parse_json(raw)
        else:  # pragma: no cover - guarded above
            raise ParseError(f"Unsupported file type '{ext}'")
    except ParseError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface any parser failure uniformly
        raise ParseError(f"Could not parse {filename}: {exc}") from exc

    if df.empty:
        raise ParseError("File parsed but contains no rows.")

    df.columns = [str(c) for c in df.columns]
    return df


def _parse_json(raw: bytes) -> pd.DataFrame:
    data = json.loads(raw.decode("utf-8"))
    if isinstance(data, list):
        return pd.DataFrame(data)
    if isinstance(data, dict):
        # {"records": [...]} style, or a dict of columns
        for value in data.values():
            if isinstance(value, list):
                return pd.DataFrame(value)
        return pd.DataFrame([data])
    raise ParseError("JSON must be an array of objects or an object of arrays.")
