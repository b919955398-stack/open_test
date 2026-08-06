"""Multiple-fault ride-through summary calculations."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from hbess_open.analysis.clause_analysis.common import ensure_parent, require_columns
from hbess_open.io.result_data import initialisation_seconds, load_case_spec, result_to_df, spec_value
from hbess_open.io.signal_dsl import ParsedDslSignal
from hbess_open.utils.progress import tqdm


DEFAULT_FAULT_TYPES = {1: "1PhG", 4: "2PhG", 7: "3PhG", 8: "PhPh", 11: "3Ph"}


def _clusters_below(series: pd.Series, threshold: float):
    mask = series < threshold
    groups = mask.ne(mask.shift(fill_value=False)).cumsum()
    return [group for _, group in series[mask].groupby(groups[mask])]


def _time_below(series: pd.Series, threshold: float) -> float:
    return float(sum(float(group.index[-1]) - float(group.index[0]) for group in _clusters_below(series, threshold)))


def _area_below(series: pd.Series, threshold: float) -> float:
    area = 0.0
    for group in _clusters_below(series, threshold):
        if len(group) > 1:
            area += float(np.trapz(threshold - group.to_numpy(dtype=float), group.index.to_numpy(dtype=float)))
    return area


def produce_s5255_mfrt_outputs(
    psout_paths: List[str],
    output_csv_path: str,
    init_time_spec_key: str,
    disturbance_command_spec_key: str,
    fault_type_command_spec_key: str,
    err_msg_spec_key: Optional[str] = None,
    operation_state_spec_key: Optional[str] = None,
    df_manipulation_fn: Optional[Callable] = None,
    vpoc_signal_name: str = "Vrms_poc_pu",
    residual_voltage_threshold: float = 0.9,
    residual_voltage_lower_band: float = 0.7,
    fault_type_enums: Optional[Mapping[int, str]] = None,
    three_phase_codes: Sequence[int] = (7, 11),
):
    rows = []
    names = dict(fault_type_enums or DEFAULT_FAULT_TYPES)

    for result_path in tqdm(psout_paths, desc="MFRT Analysis"):
        spec = load_case_spec(result_path)
        frame = result_to_df(
            result_path,
            platform="pscad",
            remove_first_seconds=initialisation_seconds(spec, init_time_spec_key),
        )
        if df_manipulation_fn is not None:
            frame = df_manipulation_fn(frame)
        require_columns(frame, (vpoc_signal_name,), Path(result_path).name)

        disturbance = ParsedDslSignal.parse(spec_value(spec, disturbance_command_spec_key)).signal
        fault_command = ParsedDslSignal.parse(spec_value(spec, fault_type_command_spec_key)).signal
        if disturbance is None or fault_command is None:
            raise ValueError("Could not parse MFRT commands for {}".format(Path(result_path).name))

        starts = [float(piece.time_start) for piece in disturbance.pieces if float(piece.target) == 1.0]
        clears = [float(piece.time_start) for piece in disturbance.pieces if float(piece.target) == 0.0]
        if len(starts) != len(clears) or not starts:
            raise ValueError("MFRT fault start/clear events do not pair in {}".format(Path(result_path).name))
        pairs = list(zip(starts, clears))

        codes = [int(float(piece.target)) for piece in fault_command.pieces if float(piece.target) != 0.0]
        if not codes and float(fault_command.initial_value) != 0.0:
            codes = [int(float(fault_command.initial_value))]
        if len(codes) == 1 and len(pairs) > 1:
            codes *= len(pairs)

        voltage = frame[vpoc_signal_name]
        below_count = 0
        band_count = 0
        for start, clear in pairs:
            window = voltage[(voltage.index >= start) & (voltage.index <= clear)]
            below_count += int((window < residual_voltage_threshold).any())
            band_count += int(((window >= residual_voltage_lower_band) & (window < residual_voltage_threshold)).any())

        gaps = [starts[index + 1] - clears[index] for index in range(len(pairs) - 1)]
        error_messages = frame[err_msg_spec_key].dropna().unique() if err_msg_spec_key in frame.columns else []
        operation_states = frame[operation_state_spec_key].dropna().unique() if operation_state_spec_key in frame.columns else []
        rows.append({
            "Name": str(spec.get("File_Name") or Path(result_path).stem),
            "Fault Times (s)": ",".join(str(round(value, 3)) for value in starts),
            "Fault Duration (s)": ",".join(str(round(clear - start, 3)) for start, clear in pairs),
            "Fault Types": ",".join(names.get(code, "Code {}".format(code)) for code in codes),
            "Minimum Time Between Faults": round(min(gaps), 3) if gaps else None,
            "Number of 3 Phase Faults": sum(code in set(three_phase_codes) for code in codes),
            "Disturbances with Residual Voltage Below 90%": below_count,
            "Disturbances with Residual Voltage Between 70-90%": band_count,
            "Time Below Vpoc of 90%": round(_time_below(voltage, residual_voltage_threshold), 3),
            "Time Integral (pu.s)": round(_area_below(voltage, residual_voltage_threshold), 4),
            "Inverter Operation States": ",".join(str(value) for value in operation_states),
            "Inverter Error Messages": ",".join(str(value) for value in error_messages),
        })

    result = pd.DataFrame(rows)
    target = ensure_parent(output_csv_path)
    result.to_csv(target, index=False)
    return result
