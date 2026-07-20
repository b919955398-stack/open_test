from __future__ import annotations

import fnmatch
import json
import math
from pathlib import Path
from typing import Dict, List, Sequence

from .output import read_csv_columns


def _select(columns: Sequence[str], patterns: Sequence[str]) -> List[str]:
    return [name for name in columns if any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)]


def plot_csv(csv_path: str, output_path: str, plot_config: Dict) -> Path:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("Plotting requires matplotlib") from exc
    data = read_csv_columns(csv_path)
    time_name = plot_config.get("time_column", "time")
    if time_name not in data:
        raise ValueError("Time column {!r} not found in {}".format(time_name, csv_path))
    panels = plot_config.get("panels") or [
        {"title": "POC Voltage", "signals": ["POC_VOLTAGE"], "ylabel": "pu"},
        {"title": "POC Active Power", "signals": ["POC_P"], "ylabel": "MW"},
        {"title": "POC Reactive Power", "signals": ["POC_Q"], "ylabel": "MVAr"},
        {"title": "Frequency", "signals": ["POC_FREQUENCY", "GRID_FREQUENCY"], "ylabel": "Hz"},
    ]
    columns = list(data.keys())
    count = len(panels)
    columns_per_page = int(plot_config.get("columns", 2))
    rows = int(math.ceil(float(count) / columns_per_page))
    fig, axes = plt.subplots(rows, columns_per_page, figsize=(6.4 * columns_per_page, 3.8 * rows), squeeze=False)
    for axis, panel in zip([item for row in axes for item in row], panels):
        names = _select(columns, panel.get("signals", []))
        for name in names:
            axis.plot(data[time_name], data[name], label=name, linewidth=1.2)
        axis.set_title(panel.get("title", ""))
        axis.set_ylabel(panel.get("ylabel", ""))
        axis.set_xlabel("Time (s)")
        axis.grid(True, alpha=0.25)
        if names:
            axis.legend(fontsize=8)
    for axis in [item for row in axes for item in row][count:]:
        axis.set_visible(False)
    fig.suptitle(Path(csv_path).stem)
    fig.tight_layout()
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(target), dpi=int(plot_config.get("dpi", 160)), bbox_inches="tight")
    plt.close(fig)
    return target


def load_plot_config(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)
