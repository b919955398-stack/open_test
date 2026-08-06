"""Maximum phase-current summary for S5.2.8 fault studies."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Mapping, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from hbess_open.analysis.clause_analysis.common import ensure_parent, nonempty_numeric, require_columns
from hbess_open.analysis.clause_analysis.fault_codes import DEFAULT_FAULT_CODE_NAMES, fault_code_name
from hbess_open.io.result_data import initialisation_seconds, load_case_spec, result_to_df, spec_value
from hbess_open.utils.progress import tqdm


def produce_s528_max_fault_current_outputs(
    psout_paths: List[str],
    output_png_path: str,
    output_csv_path: str,
    init_time_spec_key: str,
    ia_rms_ka_signal_name: str,
    ib_rms_ka_signal_name: str,
    ic_rms_ka_signal_name: str,
    x_label: str = "All fault studies",
    y_label: str = "Max current (kA)",
    title: str = "s5.2.8 Max Fault Current (excluding grid contribution)",
    df_manipulation_fn: Optional[Callable] = None,
    fault_type_spec_key: str = "Fault_Type_sig",
    fault_type_names: Optional[Mapping[int, str]] = None,
):
    rows = []
    channels = (ia_rms_ka_signal_name, ib_rms_ka_signal_name, ic_rms_ka_signal_name)
    for result_path in tqdm(psout_paths, desc="s5.2.8 Max Fault Current Studies"):
        spec = load_case_spec(result_path)
        frame = result_to_df(
            result_path,
            platform="pscad",
            remove_first_seconds=initialisation_seconds(spec, init_time_spec_key),
        )
        if df_manipulation_fn is not None:
            frame = df_manipulation_fn(frame)
        require_columns(frame, channels, Path(result_path).name)
        maxima = [float(pd.to_numeric(frame[channel], errors="raise").max()) for channel in channels]
        rows.append({
            "Name": str(spec.get("File_Name") or Path(result_path).stem),
            "Fault Type": fault_code_name(
                spec_value(spec, fault_type_spec_key), fault_type_names or DEFAULT_FAULT_CODE_NAMES
            ),
            "Max rms phase current (kA)": max(maxima),
            "Max rms current phase A (kA)": maxima[0],
            "Max rms current phase B (kA)": maxima[1],
            "Max rms current phase C (kA)": maxima[2],
        })

    result = pd.DataFrame(rows)
    csv_target = ensure_parent(output_csv_path)
    result.to_csv(csv_target, index=False)

    fault_types = ["LLLG", "LLG", "LG", "LL"]
    phase_columns = [
        ("Max rms current phase A (kA)", "#D7191C", "Phase A", -0.4),
        ("Max rms current phase B (kA)", "#2C7BB6", "Phase B", 0.0),
        ("Max rms current phase C (kA)", "green", "Phase C", 0.4),
    ]
    positions = np.arange(len(fault_types), dtype=float) * 2.0
    fig, axis = plt.subplots(figsize=(8, 9))
    for column, colour, label, offset in phase_columns:
        data = [nonempty_numeric(result.loc[result["Fault Type"] == kind, column]) for kind in fault_types]
        plot = axis.boxplot(data, positions=positions + offset, sym="", widths=0.3)
        for key in ("boxes", "whiskers", "caps", "medians"):
            plt.setp(plot[key], color=colour)
        axis.plot([], color=colour, label=label)
    axis.set_xticks(positions)
    axis.set_xticklabels([
        "{}\n(n={})".format(kind, int((result["Fault Type"] == kind).sum())) for kind in fault_types
    ])
    axis.set_xlabel(x_label)
    axis.set_ylabel(y_label)
    axis.set_title(title)
    axis.legend()
    axis.grid(True, axis="y")
    fig.tight_layout()
    png_target = ensure_parent(output_png_path)
    fig.savefig(png_target)
    plt.close(fig)
    return result
