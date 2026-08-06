"""Open PSCAD result files without the private Pallet wrapper.

The preferred reader for binary ``.psout`` files is Manitoba Hydro
International's public :mod:`mhi.psout` package.  Pickle and CSV files with the
same stem are accepted as fast, licence-free caches and are deliberately read
before the binary container.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping, Optional

import pandas as pd

from hbess_open.io.psse_out import _normalise_index


_GENERIC_CALL_NAMES = {"", "data", "pgb:data", "record", "root"}


def _variables(item) -> dict:
    try:
        return dict(item.variables())
    except Exception:
        return {}


def _candidate_name(trace) -> str:
    """Return the most useful human-readable name exposed by ``mhi.psout``."""
    trace_variables = _variables(trace)
    for key in ("Label", "Title", "Name"):
        value = str(trace_variables.get(key, "")).strip()
        if value and value.casefold() not in _GENERIC_CALL_NAMES:
            return value

    call = getattr(trace, "call", None)
    while call is not None:
        call_variables = _variables(call)
        for key in ("Name", "Label", "Title"):
            value = str(call_variables.get(key, "")).strip()
            if value and value.casefold() not in _GENERIC_CALL_NAMES:
                return value
        call = getattr(call, "parent", None)

    description = str(trace_variables.get("Description", "")).strip()
    return description or "trace_{}".format(getattr(trace, "id", "unknown"))


def _unique_name(name: str, used: set[str]) -> str:
    if name not in used:
        used.add(name)
        return name
    number = 2
    while "{}__{}".format(name, number) in used:
        number += 1
    unique = "{}__{}".format(name, number)
    used.add(unique)
    return unique


def _mapped_name(trace, automatic_name: str, channel_map: Optional[Mapping]) -> str:
    if not channel_map:
        return automatic_name
    trace_id = getattr(trace, "id", None)
    for key in (trace_id, str(trace_id), automatic_name):
        if key in channel_map:
            return str(channel_map[key])
    return automatic_name


def _mhi_file_to_df(file, run_index: int, channel_map: Optional[Mapping]) -> pd.DataFrame:
    if int(getattr(file, "num_runs", 0)) <= run_index or run_index < 0:
        raise IndexError(
            "PSOUT run_index {} is outside the available range 0..{}".format(
                run_index, max(int(getattr(file, "num_runs", 0)) - 1, 0)
            )
        )

    run = file.run(run_index)
    columns = []
    used: set[str] = set()
    for trace in run.traces():
        domain = getattr(trace, "domain", None)
        if domain is None:
            continue
        data = list(getattr(trace, "data", ()))
        index = list(getattr(domain, "data", ()))
        if not data or len(data) != len(index):
            continue
        automatic_name = _candidate_name(trace)
        name = _unique_name(_mapped_name(trace, automatic_name, channel_map), used)
        series = pd.Series(data, index=pd.Index(index, name="time"), name=name)
        if series.index.has_duplicates:
            series = series[~series.index.duplicated(keep="last")]
        columns.append(series)

    if not columns:
        raise ValueError("The selected PSOUT run contains no time-domain traces")
    return _normalise_index(pd.concat(columns, axis=1).sort_index())


def _cached_result(source: Path) -> Optional[pd.DataFrame]:
    candidates = []
    if source.suffix.lower() in {".pkl", ".pickle", ".csv"}:
        candidates.append(source)
    else:
        candidates.extend((source.with_suffix(".pkl"), source.with_suffix(".pickle"), source.with_suffix(".csv")))

    for candidate in candidates:
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() == ".csv":
            return _normalise_index(pd.read_csv(candidate))
        return _normalise_index(pd.read_pickle(candidate))
    return None


def psout_to_df(
    path,
    run_index: int = 0,
    channel_map: Optional[Mapping] = None,
    prefer_cache: bool = True,
    file_factory: Optional[Callable] = None,
) -> pd.DataFrame:
    """Read a PSCAD result into a time-indexed dataframe.

    ``file_factory`` is an injection point for testing or a compatible vendor
    reader.  In normal use it is left as ``None`` and ``mhi.psout.File`` is
    selected automatically.
    """
    source = Path(path)
    if prefer_cache or source.suffix.lower() in {".pkl", ".pickle", ".csv"}:
        cached = _cached_result(source)
        if cached is not None:
            return cached

    if source.suffix.lower() != ".psout":
        raise ValueError("Unsupported PSCAD result: {}".format(source))
    if not source.is_file():
        raise FileNotFoundError("PSCAD result does not exist: {}".format(source))

    if file_factory is None:
        try:
            import mhi.psout  # type: ignore

            file_factory = mhi.psout.File
        except Exception as exc:
            raise RuntimeError(
                "Cannot read {}. Install the official 'mhi.psout' package in "
                "this Python environment, or create an adjacent .pkl/.csv cache. "
                "Do not install the unrelated package named 'mhi'.".format(source)
            ) from exc

    try:
        with file_factory(str(source)) as file:
            return _mhi_file_to_df(file, int(run_index), channel_map)
    except Exception as exc:
        if isinstance(exc, (IndexError, ValueError)):
            raise
        raise RuntimeError("Failed to read PSCAD result {}: {}".format(source, exc)) from exc


class PscadOut:
    """Small compatibility wrapper for the former ``pallet.pscad.Psout`` API."""

    def __init__(
        self,
        path,
        run_index: int = 0,
        channel_map: Optional[Mapping] = None,
        prefer_cache: bool = True,
        file_factory: Optional[Callable] = None,
    ):
        self.path = path
        self.run_index = run_index
        self.channel_map = channel_map
        self.prefer_cache = prefer_cache
        self.file_factory = file_factory

    def to_df(self, secs_to_remove: float = 0.0) -> pd.DataFrame:
        frame = psout_to_df(
            self.path,
            run_index=self.run_index,
            channel_map=self.channel_map,
            prefer_cache=self.prefer_cache,
            file_factory=self.file_factory,
        )
        seconds = float(secs_to_remove or 0.0)
        if seconds <= 0:
            return frame
        result = frame.loc[frame.index >= seconds].copy()
        result.index = result.index - seconds
        result.index.name = "time"
        return result


Psout = PscadOut
