"""Shared result and sidecar helpers used by PSS/E and PSCAD analyses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Optional

import pandas as pd

from hbess_open.io.pscad_out import psout_to_df
from hbess_open.io.psse_out import out_to_df


def companion_path(result_path, suffix: str) -> Path:
    return Path(result_path).with_suffix(suffix)


def load_case_spec(result_path) -> dict:
    path = companion_path(result_path, ".json")
    if not path.is_file():
        raise FileNotFoundError("Missing result metadata sidecar: {}".format(path))
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def spec_value(spec: Mapping, key: str, default=None):
    if key in spec:
        return spec[key]
    substitutions = spec.get("substitutions")
    if isinstance(substitutions, Mapping) and key in substitutions:
        return substitutions[key]
    if default is not None:
        return default
    raise KeyError("SPEC key {!r} was not found at top level or in substitutions".format(key))


def initialisation_seconds(spec: Mapping, key: str = "TIME_Full_Init_Time_sec") -> float:
    value = spec_value(spec, key, 0.0)
    if value in (None, ""):
        return 0.0
    return float(value)


def result_to_df(
    path,
    platform: Optional[str] = None,
    remove_first_seconds: float = 0.0,
    psse_config: Optional[Mapping] = None,
    psout_run_index: int = 0,
    channel_map: Optional[Mapping] = None,
) -> pd.DataFrame:
    source = Path(path)
    suffix = source.suffix.lower()
    selected = str(platform or "").strip().lower()
    if not selected:
        selected = "pscad" if suffix == ".psout" else "psse" if suffix == ".out" else "generic"

    if selected == "pscad":
        frame = psout_to_df(source, run_index=psout_run_index, channel_map=channel_map)
    elif selected == "psse":
        frame = out_to_df(source, psse_config=psse_config)
    elif suffix in {".pkl", ".pickle"}:
        frame = out_to_df(source)
    elif suffix == ".csv":
        frame = out_to_df(source)
    else:
        raise ValueError("Unsupported result platform or extension: {}".format(source))

    seconds = float(remove_first_seconds or 0.0)
    if seconds > 0:
        frame = frame.loc[frame.index >= seconds].copy()
        frame.index = frame.index - seconds
        frame.index.name = "time"
    return frame


class SimulationOut:
    """Format-neutral ``Out(...).to_df()`` compatibility wrapper."""

    def __init__(self, path, platform: Optional[str] = None, **options):
        self.path = path
        self.platform = platform
        self.options = options

    def to_df(self, secs_to_remove: float = 0.0) -> pd.DataFrame:
        return result_to_df(
            self.path,
            platform=self.platform,
            remove_first_seconds=secs_to_remove,
            **self.options,
        )


Out = SimulationOut
