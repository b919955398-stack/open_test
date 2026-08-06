"""Small shared utilities for clause-analysis implementations."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


def ensure_parent(path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def require_columns(frame: pd.DataFrame, columns: Iterable[str], case_name: str = "result") -> None:
    missing = [str(column) for column in columns if column not in frame.columns]
    if missing:
        raise KeyError("{} is missing channel(s): {}".format(case_name, ", ".join(missing)))


def enum_code(value):
    number = float(value)
    return int(number) if number.is_integer() else number


def nonempty_numeric(values):
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    return series.to_numpy() if not series.empty else [float("nan")]
