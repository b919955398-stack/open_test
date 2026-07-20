"""PSS/E output reader without the Pallet ``Out`` wrapper.

The native runner always writes a CSV beside each OUT file, so post-processing
normally works without importing PSS/E. For an older OUT-only result directory,
the reader can use Siemens ``dyntools`` when a PSS/E configuration is supplied.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional

import pandas as pd


def _normalise_index(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    time_column = next(
        (name for name in result.columns if str(name).strip().lower() in {"time", "time(s)", "time (s)"}),
        None,
    )
    if time_column is not None:
        result.index = pd.to_numeric(result.pop(time_column), errors="raise")
    else:
        result.index = pd.to_numeric(result.index, errors="raise")
    result.index.name = "time"
    return result


def out_to_df(path, psse_config: Optional[Mapping] = None) -> pd.DataFrame:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".csv":
        return _normalise_index(pd.read_csv(source))
    if suffix in {".pkl", ".pickle"}:
        return _normalise_index(pd.read_pickle(source))

    csv_path = source.with_suffix(".csv")
    if csv_path.exists():
        return _normalise_index(pd.read_csv(csv_path))
    if suffix != ".out":
        raise ValueError("Unsupported simulation output: {}".format(source))

    try:
        if psse_config is None:
            import dyntools  # type: ignore
        else:
            from psse_open.bootstrap import import_psse

            _psspy, dyntools = import_psse(dict(psse_config))
        channel_file = dyntools.CHNF(str(source), outvrsn=0)
        _title, channel_ids, channel_data = channel_file.get_data()
    except Exception as exc:
        raise RuntimeError(
            "Cannot read {}. The adjacent CSV is missing and Siemens dyntools "
            "is unavailable. Run replotting with the matching PSS/E Python, or "
            "regenerate the case with this native runner.".format(source)
        ) from exc

    data = {"time": channel_data["time"]}
    for key, label in channel_ids.items():
        if key != "time":
            data[str(label)] = channel_data[key]
    return _normalise_index(pd.DataFrame(data))


class PsseOut:
    def __init__(self, path, psse_config: Optional[Mapping] = None):
        self.path = path
        self.psse_config = psse_config

    def to_df(self) -> pd.DataFrame:
        return out_to_df(self.path, self.psse_config)


Out = PsseOut
