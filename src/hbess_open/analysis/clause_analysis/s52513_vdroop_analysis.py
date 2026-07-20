import os
import json
import pandas as pd
from hbess_open.utils.progress import tqdm
from typing import List, Tuple, Optional, Callable
import sys
from hbess_open.analysis.gridlink.characteristic_overlays import make_characteristic_overlay
from hbess_open.io.psse_out import PsseOut as Out
from hbess_open.io.signal_dsl import ParsedDslSignal


def produce_vdroop_outputs(
        psout_paths : List[str],
        output_png_path : str,
        output_csv_path : str,
        qpoc_mvar_signal_name : str,
        vpoc_rms_pu_signal_name : str,
        vref_pu_signal_name : str,
        vpoc_pu_command_spec_key : str,
        vdroop_characteristic_points : List[Tuple[float, float]],
        init_time_spec_key : str,
        df_manipulation_fn : Optional[Callable] = None,
        x86 : bool = True
        ):
    
    results_df = pd.DataFrame(columns=[
        "Name",
        "Step No",
        "Vpoc (pu)",
        "Vref (pu)",
        "Verr (pu)",
        "Qpoc (MVAr)",
    ])

    if not x86:
        raise NotImplementedError("This native package contains the PSS/E analysis path only")
    extension = ".out"


    for i in tqdm(range(len(psout_paths)), desc="dQ/dV studies"):
        psout_path = psout_paths[i]
        json_path = psout_path.split(extension)[0] + ".json"

        with open(json_path, 'r') as f:
            spec = json.load(f)
        
        
        df = Out(psout_path).to_df()

        if df_manipulation_fn is not None:
            df = df_manipulation_fn(df)

        df_copy = df
        if not x86:
            init_time_sec = float(spec["substitutions"][init_time_spec_key])
            df_copy = df_copy[df_copy.index > init_time_sec]
            df_copy.index = df_copy.index - init_time_sec
        df = df_copy


        vpoc_cmd = ParsedDslSignal.parse(spec[vpoc_pu_command_spec_key]).signal
        assert vpoc_cmd is not None
        settled_times = [piece.time_start - 0.1 for piece in vpoc_cmd.pieces] + [max(df.index)]

        for j, settled_time in enumerate(settled_times):
            filtered_df = df[df.index < settled_time]

            new_row = {
                "Name": os.path.basename(psout_path).split(extension)[0],
                "Step No": j+1,
                "Vpoc (pu)": filtered_df[vpoc_rms_pu_signal_name].iloc[-1],
                "Vref (pu)": filtered_df[vref_pu_signal_name].iloc[-1],
                "Verr (pu)": None,
                "Qpoc (MVAr)": filtered_df[qpoc_mvar_signal_name].iloc[-1],
                }
            results_df = pd.concat([results_df, pd.DataFrame([new_row])], ignore_index=True)

    results_df["Verr (pu)"] = results_df["Vpoc (pu)"] - results_df["Vref (pu)"]

    make_characteristic_overlay(
        output_path=output_png_path,
        points = list(zip(results_df["Verr (pu)"], results_df["Qpoc (MVAr)"])),
        saturated_points=None, 
        characteristic_points=vdroop_characteristic_points,
        title="Voltage Droop Response",
        y_label=u'Reactive Power, Q (MVAr)',
        x_label=u'Voltage Error, $V_{error}$ (pu)',
        points_colour='red',
        characteristic_colour='black',
        saturated_points_label = None,
        saturated_points_colour = 'grey',
        points_label = "Measured Values",
        characteristic_label = "Characteristic",
        points_additional_args={"marker": "x"},
        saturated_points_additional_args={"marker": "o"},
        characteristic_additional_args={"linestyle": '--'},
    )   
    results_df.to_csv(output_csv_path, index=False)







