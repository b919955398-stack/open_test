"""Healthy-phase voltage checks for balanced and unbalanced faults."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Mapping, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from hbess_open.analysis.clause_analysis.common import ensure_parent, enum_code, nonempty_numeric, require_columns
from hbess_open.io.result_data import initialisation_seconds, load_case_spec, result_to_df, spec_value
from hbess_open.io.signal_dsl import ParsedDslSignal
from hbess_open.utils.progress import tqdm


def conduct_phase_voltage_analysis(
    psout_paths: List[str],
    output_png_path: str,
    output_csv_path: str,
    timing_cmd_spec_key: str,
    fault_type_cmd_spec_key: str,
    fault_type_enums: Mapping,
    healthy_phase_enums: Mapping,
    phA_channel_key: str,
    phB_channel_key: str,
    phC_channel_key: str,
    groupby_str_for_plot_title: Optional[str] = None,
    init_time_spec_key: str = "TIME_Full_Init_Time_sec",
    time_shift_sec: float = 0.01,
    df_manipulation_fn: Optional[Callable] = None,
):
    rows = []
    phase_channels = {"Phase A": phA_channel_key, "Phase B": phB_channel_key, "Phase C": phC_channel_key}

    for result_path in tqdm(psout_paths, desc="Phase Voltage Health Analysis"):
        spec = load_case_spec(result_path)
        frame = result_to_df(
            result_path,
            platform="pscad",
            remove_first_seconds=initialisation_seconds(spec, init_time_spec_key),
        )
        if df_manipulation_fn is not None:
            frame = df_manipulation_fn(frame)
        require_columns(frame, phase_channels.values(), Path(result_path).name)

        timing = ParsedDslSignal.parse(spec_value(spec, timing_cmd_spec_key)).signal
        fault_command = ParsedDslSignal.parse(spec_value(spec, fault_type_cmd_spec_key)).signal
        if timing is None or fault_command is None:
            raise ValueError("Could not parse phase-health commands for {}".format(Path(result_path).name))
        starts = [float(piece.time_start) for piece in timing.pieces if float(piece.target) == 1.0]
        clears = [float(piece.time_start) for piece in timing.pieces if float(piece.target) == 0.0]
        if len(starts) != len(clears) or not starts:
            raise ValueError("Fault start/clear events do not pair in {}".format(Path(result_path).name))

        fault_codes = [enum_code(piece.target) for piece in fault_command.pieces if float(piece.target) != 0.0]
        if not fault_codes:
            fault_codes = [enum_code(fault_command.initial_value)]
        if len(fault_codes) == 1 and len(clears) > 1:
            fault_codes *= len(clears)
        if len(fault_codes) != len(clears):
            raise ValueError("Fault type count does not match fault count in {}".format(Path(result_path).name))

        filename = str(spec.get("File_Name") or Path(result_path).stem)
        fault_level = spec.get("Grid_FL_MVA_sig")
        for index, (start, clear, code) in enumerate(zip(starts, clears, fault_codes)):
            in_fault_time = clear - float(time_shift_sec)
            in_fault_window = frame.loc[frame.index <= in_fault_time]
            if in_fault_window.empty:
                raise ValueError("No in-fault sample for fault {} in {}".format(index + 1, filename))
            in_fault = {phase: float(in_fault_window[channel].iloc[-1]) for phase, channel in phase_channels.items()}

            post_end = starts[index + 1] - float(time_shift_sec) if index + 1 < len(starts) else float(frame.index[-1])
            post_window = frame[(frame.index >= clear + float(time_shift_sec)) & (frame.index <= post_end)]
            if post_window.empty:
                raise ValueError("No post-fault sample for fault {} in {}".format(index + 1, filename))
            post_fault = {phase: float(post_window[channel].max()) for phase, channel in phase_channels.items()}

            healthy = list(healthy_phase_enums.get(code, ()))
            healthy_values = [in_fault[phase] for phase in healthy if phase in in_fault]
            suffix = "_FAULT{}".format(index + 1) if len(clears) > 1 else ""
            rows.append({
                "Name": filename + suffix,
                "Fault Type": fault_type_enums.get(code, "undefined"),
                "In-Fault Voltage Phase A (pu)": in_fault["Phase A"],
                "In-Fault Voltage Phase B (pu)": in_fault["Phase B"],
                "In-Fault Voltage Phase C (pu)": in_fault["Phase C"],
                "In-Fault Max Phase Voltage (pu)": max(healthy_values) if healthy_values else np.nan,
                "In-Fault Min Phase Voltage (pu)": min(healthy_values) if healthy_values else np.nan,
                "Post-Fault Voltage Phase A (pu)": post_fault["Phase A"],
                "Post-Fault Voltage Phase B (pu)": post_fault["Phase B"],
                "Post-Fault Voltage Phase C (pu)": post_fault["Phase C"],
                "Post-Fault Max Phase Voltage (pu)": max(post_fault.values()),
                "Post-Fault Min Phase Voltage (pu)": min(post_fault.values()),
                "Fault Level": fault_level,
            })

    result = pd.DataFrame(rows)
    csv_target = ensure_parent(output_csv_path)
    result.to_csv(csv_target, index=False)

    title_suffix = " ({})".format(groupby_str_for_plot_title) if groupby_str_for_plot_title else ""
    fig, axes = plt.subplots(1, 2, figsize=(16, 9))
    in_types = ["1PhG", "2PhG", "PhPh"]
    post_types = ["1PhG", "2PhG", "PhPh", "3PhG"]
    in_data = [nonempty_numeric(result.loc[result["Fault Type"] == kind, "In-Fault Max Phase Voltage (pu)"]) for kind in in_types]
    post_data = [nonempty_numeric(result.loc[result["Fault Type"] == kind, "Post-Fault Max Phase Voltage (pu)"]) for kind in post_types]
    axes[0].boxplot(in_data, widths=0.4)
    axes[0].set_xticklabels(["{}\n(n={})".format(kind, int((result["Fault Type"] == kind).sum())) for kind in in_types])
    axes[0].set_title("In-Fault Healthy Phase Voltages" + title_suffix)
    axes[0].set_ylabel("Max In-Fault POC Voltage (pu)")
    axes[1].boxplot(post_data, widths=0.4)
    axes[1].set_xticklabels(["{}\n(n={})".format(kind, int((result["Fault Type"] == kind).sum())) for kind in post_types])
    axes[1].set_title("Post-Fault Phase Voltages" + title_suffix)
    axes[1].set_ylabel("Max Post-Fault POC Voltage (pu)")
    for axis in axes:
        axis.grid(True)
    fig.suptitle("Phase Voltage Health")
    fig.tight_layout()
    png_target = ensure_parent(output_png_path)
    fig.savefig(png_target)
    plt.close(fig)
    return result
