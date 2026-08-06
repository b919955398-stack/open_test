"""S5.2.5.8 inverter protection trip-time extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

import numpy as np
import pandas as pd

from hbess_open.analysis.clause_analysis.common import ensure_parent, require_columns
from hbess_open.io.result_data import initialisation_seconds, load_case_spec, result_to_df
from hbess_open.utils.progress import tqdm


def calculate_s5258_protection_trip_time(
    x86: bool,
    out_paths: List[str],
    output_csv_path: str,
    inv_active_p_signal_name: str,
    inv_vrms_lv_pu_signal_name: str,
    inv_debug_grierr_signal_name: str,
    trip_threshold: float = 0.0,
    init_time_spec_key: str = "TIME_Full_Init_Time_sec",
    df_manipulation_fn: Optional[Callable] = None,
):
    rows = []
    for result_path in tqdm(out_paths, desc="Protection Time Analysis"):
        spec = load_case_spec(result_path)
        remove_seconds = 0.0 if x86 else initialisation_seconds(spec, init_time_spec_key)
        frame = result_to_df(
            result_path,
            platform="psse" if x86 else "pscad",
            remove_first_seconds=remove_seconds,
        )
        if df_manipulation_fn is not None:
            frame = df_manipulation_fn(frame)
        columns = (inv_active_p_signal_name, inv_vrms_lv_pu_signal_name, inv_debug_grierr_signal_name)
        require_columns(frame, columns, Path(result_path).name)
        detected = frame.loc[frame[inv_debug_grierr_signal_name] > float(trip_threshold)]
        if detected.empty:
            trip_time = np.nan
            active_power = np.nan
            voltage = np.nan
            trip_detected = False
        else:
            first = detected.iloc[0]
            trip_time = float(detected.index[0])
            active_power = float(first[inv_active_p_signal_name])
            voltage = float(first[inv_vrms_lv_pu_signal_name])
            trip_detected = True
        rows.append({
            "Name": str(spec.get("File_Name") or Path(result_path).stem),
            "Trip Detected": trip_detected,
            "Trip Time (sec)": trip_time,
            "Inverter Active Power (MW)": active_power,
            "Voltage (pu)": voltage,
        })

    result = pd.DataFrame(rows)
    target = ensure_parent(output_csv_path)
    result.to_csv(target, index=False)
    return result


def prot_trip_analysis(psout_paths, output_dir, **kwargs):
    """Compatibility wrapper used by older GridLink scripts."""
    output_path = Path(output_dir) / "Protection Trip Time Analysis.csv"
    return calculate_s5258_protection_trip_time(
        x86=False,
        out_paths=list(psout_paths),
        output_csv_path=str(output_path),
        **kwargs
    )
