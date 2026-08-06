import os
import json
import pandas as pd
import numpy as np
from typing import List, Callable, Optional
from hbess_open.utils.progress import tqdm
import pickle

from hbess_open.analysis.gridlink.rise_settle_plots import produce_rise_settle_recovery_plot
from hbess_open.analysis.gridlink.settling_analysis import analyse_step
from hbess_open.io.result_data import SimulationOut as Out, initialisation_seconds
from hbess_open.io.signal_dsl import ParsedDslSignal

def produce_s5255_rise_settle_recovery_curve(
        psout_paths : List[str],
        output_dir : str,
        disturbance_command_spec_key : str,
        vpoc_pu_signal_name : str,
        ppoc_mw_signal_name : str,
        iq_pu_signal_name : str,
        rise_settle_title_spec_key : str,
        pre_step_plot_secs : float = 2.0,
        commencement_thresholds: Optional[List[float]] = None,
        frt_flag_signal_name : Optional[str] = None,
        frt_flag_active_values: Optional[List[float]] = None,
        df_manipulation_fn : Optional[Callable] = None,
        x86 : bool = True,
        ):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    results_df = pd.DataFrame(columns=[
        "Name",
        "Iq Settling Time (sec)",
        "Iq Rise Time (sec)",
        "Ppoc Recovery Time (sec)",
        ])

    for i in tqdm(range(len(psout_paths)), desc="Rise, Settle, Recovery Time Analysis"):

        TIME_SHIFT_SEC = 0.01
        MIN_RISE_TIME_FROM_FAULT_SEC = 0.00
        psout_path = psout_paths[i]
        extension = "."+psout_path.split(".")[-1]
        json_path = psout_path.split(extension)[0] + ".json"

        with open(json_path, 'r') as f:
            spec = json.load(f)

        

        # if "Readable_Name" in spec:
            # simulation_name = spec["Readable_Name"]
        # else:
        simulation_name = spec["File_Name"]

        if extension == ".pkl":
            df = pd.read_pickle(psout_path)
        else:
            df = Out(psout_path).to_df()

        if df_manipulation_fn is not None:
            df = df_manipulation_fn(df)

        df_copy = df
        if not x86:
            init_time_sec = initialisation_seconds(spec)
            df_copy = df_copy[df_copy.index > init_time_sec]
            df_copy.index = df_copy.index - init_time_sec
        df = df_copy

        disturbance_cmd = ParsedDslSignal.parse(spec[disturbance_command_spec_key]).signal
        assert disturbance_cmd is not None
        step_times = [piece.time_start for piece in disturbance_cmd.pieces]

        #TIME SHIFT SEC is used so that we can include a brief moment before the fault that can be passed in to analyse_step
        init_fault_times = [piece.time_start - TIME_SHIFT_SEC for piece in disturbance_cmd.pieces if piece.target==1.0]
        clear_fault_times = [piece.time_start - TIME_SHIFT_SEC for piece in disturbance_cmd.pieces if piece.target==0.0]
        init_clear_pairs = list(zip(init_fault_times,clear_fault_times))

        for j, (init_fault_time, clear_fault_time) in enumerate(init_clear_pairs):

            if j == len(init_clear_pairs) - 1:
                iq_analysis_df = df[(df.index >= init_fault_time) & (df.index < clear_fault_time)]
                p_analysis_df = df[df.index >= clear_fault_time]
                step_plot_df = df[(df.index >= init_fault_time - pre_step_plot_secs)]

            else:
                iq_analysis_df = df[(df.index >= init_fault_time) & (df.index < clear_fault_time)]
                p_analysis_df = df[(df.index >= clear_fault_time) & (df.index < init_clear_pairs[j+1][0])]
                step_plot_df = df[(df.index >= init_fault_time - pre_step_plot_secs) & (df.index < init_clear_pairs[j+1][0])]

            p_recovery_target = df[df.index <= init_fault_time].iloc[-1][ppoc_mw_signal_name]*0.95

            commmencement_results = analyse_step(
                series=iq_analysis_df[iq_pu_signal_name],
                series2=iq_analysis_df[vpoc_pu_signal_name],
                commencement_thresholds=commencement_thresholds
            )

            p_results = analyse_step(
                series=p_analysis_df[ppoc_mw_signal_name],
                recovery_target_mw=p_recovery_target,
                select_first_recovery=True
                )
            iq_results = analyse_step(
                series=iq_analysis_df[iq_pu_signal_name]
                )


            scenario_basename = simulation_name
            rise_settle_filepath = os.path.join(output_dir, f"{scenario_basename}_Step_{j+1}.png")

            if len(step_times) > 1:
                rise_settle_plot_title = spec[rise_settle_title_spec_key]
            else:
                rise_settle_plot_title = f"{spec[rise_settle_title_spec_key]} Step {j+1}"

            produce_rise_settle_recovery_plot(
                    title=rise_settle_plot_title,
                    output_png_path=rise_settle_filepath,
                    subtitle=None,
                    ppoc_mw_series=step_plot_df[ppoc_mw_signal_name],
                    iq_pu_series=step_plot_df[iq_pu_signal_name],
                    vpoc_pu_series=step_plot_df[vpoc_pu_signal_name],
                    p_results=p_results,
                    iq_results=iq_results,
                    fault_clearance_time=clear_fault_time+TIME_SHIFT_SEC,
                    fault_inception_time=init_fault_time+TIME_SHIFT_SEC
                    )
            
            frt_analysis_performed = False
            # if frt_flag_signal_name is not None:
            #     if len(frt_flag_active_values) == 0:
            #         print("Warning, no values provided for when the FRT flag signal should be considered active")
            # else:
            if frt_flag_signal_name not in df.columns.tolist():
                print("Warning; FRT Flag Signal Name is not in dataframe")
            else:
                count_frt = df[df[frt_flag_signal_name].isin(frt_flag_active_values)].shape[0]
                print(count_frt)
                # cumulative_frt_time = count_frt * time_step
                frt_analysis_performed = True
            
            new_row = {
                    "Name": scenario_basename,
                    "Iq Settling Time (sec)": iq_results.settling_time_results.settling_time_sec,
                    "Iq Rise Time (sec)": iq_results.rise_time_results.rise_time_sec,
                    "Ppoc Recovery Time (sec)": p_results.p_recovery_time_results.p_recovery_time_sec,
                    "Enters FRT" : count_frt > 0 if frt_analysis_performed else None,
                    "Iq Commencement Time (sec)": commmencement_results.CommencementTimeResults.commencement_time_sec,
                    # "Cumulative FRT time": cumulative_frt_time if frt_analysis_performed else None,
                }

            results_df = pd.concat([results_df, pd.DataFrame([new_row])], ignore_index=True)
    results_df.to_csv(os.path.join(output_dir,"s5255_rise_settle_recovery_times.csv"), index=False)


