from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict


def out_to_csv(out_path: str, csv_path: str, dyntools, nominal_frequency_hz: float = 50.0) -> Path:
    out_file, csv_file = Path(out_path), Path(csv_path)
    channel_file = dyntools.CHNF(str(out_file), outvrsn=0)
    _title, channel_ids, channel_data = channel_file.get_data()
    keys = ["time"] + [key for key in channel_ids.keys() if key != "time"]
    labels = ["time"] + [str(channel_ids[key]) for key in keys[1:]]
    rows = zip(*[channel_data[key] for key in keys])
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_file, "w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(labels)
        for row in rows:
            converted = []
            for label, value in zip(labels, row):
                numeric = float(value)
                if "_FREQUENCY" in label:
                    numeric = numeric * float(nominal_frequency_hz) + float(nominal_frequency_hz)
                elif "_PELEC" in label or "_QELEC" in label:
                    numeric *= 100.0
                converted.append(numeric)
            writer.writerow(converted)
    return csv_file


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
