from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict


def _unique_label(label: str, counts: Dict[str, int]) -> str:
    """Match pandas' duplicate-column convention without a CSV round trip."""
    count = counts.get(label, 0)
    counts[label] = count + 1
    return label if count == 0 else "{}.{}".format(label, count)


def out_to_dataframe(out_path: str, dyntools, nominal_frequency_hz: float = 50.0):
    """Decode one PSS/E OUT directly into a pandas DataFrame.

    The former path wrote every sample to a temporary CSV and immediately read
    the same file back into pandas for plotting.  Decoding once in memory keeps
    the numeric result identical while removing that disk round trip.  CSV is
    still available through :func:`write_dataframe_csv` when explicitly kept
    or when a failed plot needs a diagnostic file.
    """
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("OUT decoding requires pandas") from exc

    out_file = Path(out_path)
    channel_file = dyntools.CHNF(str(out_file), outvrsn=0)
    _title, channel_ids, channel_data = channel_file.get_data()
    keys = [key for key in channel_ids.keys() if key != "time"]
    counts: Dict[str, int] = {"time": 1}
    data: Dict[str, Any] = {"time": channel_data["time"]}
    for key in keys:
        label = _unique_label(str(channel_ids[key]), counts)
        data[label] = channel_data[key]

    frame = pd.DataFrame(data)
    frame["time"] = pd.to_numeric(frame["time"], errors="raise")
    for label in frame.columns:
        if label == "time":
            continue
        frame[label] = pd.to_numeric(frame[label], errors="raise")
        if "_FREQUENCY" in label:
            frame[label] = frame[label] * float(nominal_frequency_hz) + float(
                nominal_frequency_hz
            )
        elif "_PELEC" in label or "_QELEC" in label:
            frame[label] = frame[label] * 100.0
    return frame


def write_dataframe_csv(dataframe, csv_path: str) -> Path:
    csv_file = Path(csv_path)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(str(csv_file), index=False)
    return csv_file


def out_to_csv(out_path: str, csv_path: str, dyntools, nominal_frequency_hz: float = 50.0) -> Path:
    frame = out_to_dataframe(out_path, dyntools, nominal_frequency_hz)
    return write_dataframe_csv(frame, csv_path)


def read_csv_columns(path: str) -> Dict[str, list]:
    with open(path, "r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        result: Dict[str, list] = {name: [] for name in (reader.fieldnames or [])}
        for row in reader:
            for name in result:
                try:
                    result[name].append(float(row[name]))
                except (TypeError, ValueError):
                    result[name].append(row[name])
        return result
