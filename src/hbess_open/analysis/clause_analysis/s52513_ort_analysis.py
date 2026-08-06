"""S5.2.5.13 oscillatory response test (ORT) summary plots."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import pandas as pd

from hbess_open.analysis.clause_analysis.common import ensure_parent, require_columns
from hbess_open.io.result_data import initialisation_seconds, load_case_spec, result_to_df, spec_value
from hbess_open.io.signal_dsl import ParsedDslSignal
from hbess_open.utils.progress import tqdm


@dataclass
class SubplotData:
    osc_freq_hz: float
    vpoc_pu: pd.Series
    qpoc_mvar: pd.Series


def produce_ort_plots(
    psout_paths: List[str],
    vslack_osc_freq_spec_key: str,
    vslack_osc_amp_spec_key: str,
    vpoc_channel_key: str,
    qpoc_channel_key: str,
    output_path: str,
    periods_per_subplot: float,
    init_time_spec_key: str = "TIME_Full_Init_Time_sec",
):
    if not psout_paths:
        raise ValueError("ORT analysis received no result files")
    if periods_per_subplot <= 0:
        raise ValueError("periods_per_subplot must be greater than zero")

    columns = 3
    rows = int(math.ceil(len(psout_paths) / float(columns)))
    fig, axes = plt.subplots(rows, columns, squeeze=False, figsize=(7.1 * columns, 3.15 * rows))
    axes_flat = axes.ravel()

    for index, result_path in enumerate(tqdm(psout_paths, desc="Preparing ORT Summary Plot")):
        spec = load_case_spec(result_path)
        command = ParsedDslSignal.parse(spec_value(spec, vslack_osc_amp_spec_key)).signal
        if command is None or not command.pieces:
            raise ValueError("Could not find ORT start time in {}".format(Path(result_path).name))
        frequency = float(spec_value(spec, vslack_osc_freq_spec_key))
        if frequency <= 0:
            raise ValueError("ORT frequency must be greater than zero in {}".format(Path(result_path).name))

        frame = result_to_df(
            result_path,
            platform="pscad",
            remove_first_seconds=initialisation_seconds(spec, init_time_spec_key),
        )
        require_columns(frame, (vpoc_channel_key, qpoc_channel_key), Path(result_path).name)
        data = SubplotData(frequency, frame[vpoc_channel_key], frame[qpoc_channel_key])

        start = float(command.pieces[0].time_start)
        duration = periods_per_subplot / data.osc_freq_hz
        plot_start = max(0.0, start - 0.1 * duration)
        plot_end = start + duration
        voltage = data.vpoc_pu[(data.vpoc_pu.index >= plot_start) & (data.vpoc_pu.index <= plot_end)]
        reactive = data.qpoc_mvar[(data.qpoc_mvar.index >= plot_start) & (data.qpoc_mvar.index <= plot_end)]
        if voltage.empty or reactive.empty:
            raise ValueError("ORT window contains no samples in {}".format(Path(result_path).name))

        axis = axes_flat[index]
        reactive_axis = axis.twinx()
        axis.plot(voltage.index, voltage, color="tab:blue", label="Vpoc")
        reactive_axis.plot(reactive.index, reactive, color="tab:red", linestyle="--", label="Qpoc")
        axis.set_title("{} Hz".format(frequency), loc="left")
        axis.set_xlabel("Time (s)")
        axis.set_ylabel("Vpoc (pu)", color="tab:blue")
        reactive_axis.set_ylabel("Qpoc (MVAr)", color="tab:red")
        axis.grid(True)

    for axis in axes_flat[len(psout_paths):]:
        axis.set_visible(False)
    fig.tight_layout()
    target = ensure_parent(output_path)
    fig.savefig(target, bbox_inches="tight")
    plt.close(fig)
    return str(target)
