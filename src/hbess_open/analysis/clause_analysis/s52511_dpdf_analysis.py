import os
import glob
import json
import pandas as pd
from typing import List, Tuple, Callable, Optional
from hbess_open.utils.progress import tqdm
from hbess_open.analysis.gridlink.characteristic_overlays import make_characteristic_overlay
from hbess_open.io.psse_out import PsseOut as Out
from hbess_open.io.signal_dsl import ParsedDslSignal


def produce_s52511_dpdf_outputs(
        psout_paths : List[str],
        output_png_path: str,
        output_csv_path: str,
        init_time_spec_key : str,
        pref_mw_signal_name : str,
        ppoc_mw_signal_name : str,
        fpoc_hz_signal_name : str,
        fslack_hz_command_spec_key : str,
        dpdf_characteristic_points : List[Tuple[float, float]],
        pmax_mw : float,
        pmin_mw : float,
        p_saturation_tolerance_mw : float = 5.0,
        df_manipulation_fn : Optional[Callable] = None,
        x86 : bool = True
        ):

    if not x86:
        raise NotImplementedError("This native package contains the PSS/E analysis path only")
    extension = ".out"

    results_df = pd.DataFrame(columns=["Name", "Step No.", "Δf", "ΔP", "Saturated"])
    for i in tqdm(range(len(psout_paths)), desc="dP/df studies"):
        psout_path = psout_paths[i]
        json_path = psout_path.split(extension)[0] + ".json"

        with open(json_path, 'r') as f:
            spec = json.load(f)
        
    
        if "Readable_Name" in spec:
            simulation_name = spec["Readable_Name"]
        else:
            simulation_name = spec["File_Name"]


        df = Out(psout_path).to_df()

        if df_manipulation_fn is not None:
            df = df_manipulation_fn(df)

        df_copy = df
        if not x86:
            init_time_sec = float(spec["substitutions"][init_time_spec_key])
            df_copy = df_copy[df_copy.index > init_time_sec]
            df_copy.index = df_copy.index - init_time_sec
        df = df_copy




        fslack_cmd = ParsedDslSignal.parse(spec[fslack_hz_command_spec_key]).signal
        settled_times = [piece.time_start - 0.1 for piece in fslack_cmd.pieces] + [max(df.index)]

        for j, settled_time in enumerate(settled_times):
            filtered_df = df[df.index < settled_time]
            last_fmeas_hz = filtered_df[fpoc_hz_signal_name].iloc[-1]
            last_pref_mw = filtered_df[pref_mw_signal_name].iloc[-1]
            last_pmeas_mw = filtered_df[ppoc_mw_signal_name].iloc[-1]
            last_deltap_mw = last_pmeas_mw - last_pref_mw
            last_deltaf_hz = last_fmeas_hz - 50.0

            p_distance_from_saturation_mw = abs(last_pmeas_mw - pmax_mw), abs(last_pmeas_mw - pmin_mw) 
            p_saturated = min(p_distance_from_saturation_mw) < p_saturation_tolerance_mw

            new_row = {
                    "Name": simulation_name,
                    "Δf": last_deltaf_hz,
                    "Step No.": j+1,
                    "ΔP": last_deltap_mw,
                    "Saturated": p_saturated,
                }

            results_df = pd.concat([results_df, pd.DataFrame([new_row])], ignore_index=True)

    results_df.to_csv(output_csv_path, index=False)

    make_characteristic_overlay(
        output_path=output_png_path,
        points=list(results_df.loc[results_df["Saturated"] == False, ["Δf", "ΔP"]].itertuples(index=False, name=None)),
        saturated_points=list(results_df.loc[results_df["Saturated"] == True, ["Δf", "ΔP"]].itertuples(index=False, name=None)),
        characteristic_points=dpdf_characteristic_points,
        title="Frequency response",
        y_label=u'ΔP',
        x_label=u'Δf',
        points_colour='red',
        characteristic_colour='black',
        characteristic_label="Characteristic",
        points_additional_args={"marker": "x"},
        saturated_points_additional_args={"marker": 'o'},
        characteristic_additional_args={"linestyle": '--'},
        )    
