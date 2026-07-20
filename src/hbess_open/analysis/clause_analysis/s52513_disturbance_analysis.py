import os
import json
import pandas as pd
from hbess_open.utils.progress import tqdm
from typing import List, Optional, Callable

from hbess_open.analysis.gridlink.disturbance_tracking_plots import produce_disturbance_tracking_plot_pqv
from hbess_open.analysis.gridlink.rise_settle_plots import produce_rise_settle_plot_pqv
from hbess_open.analysis.gridlink.settling_analysis import StepAnalysisResults, analyse_step
from hbess_open.io.psse_out import out_to_df
from hbess_open.io.signal_dsl import ParsedDslSignal


def produce_disturbance_analysis_outputs(
        psout_paths : List[str],
        output_png_path: str,
        output_csv_path : str,
        disturbance_command_spec_key : str,
        ppoc_mw_signal_name : str,
        qpoc_mvar_signal_name : str,
        vpoc_pu_signal_name : str,
        perr_mw_signal_name : str,
        qerr_mvar_signal_name : str,
        verr_adj_pu_signal_name : str,
        rise_settle_title_spec_key : str,
        init_time_spec_key : str,
        rise_settle_plots_subdir_name: str = "rise_settle_plots",
        pre_step_plot_secs : float = 2.0,
        pre_error_plot_secs : float = 2.0,
        df_manipulation_fn : Optional[Callable] = None,
        x86 = True,
        ):

    if not x86:
        raise NotImplementedError("This native package contains the PSS/E analysis path only")
    extension = ".out"

    rise_settle_plots_subdir_path = os.path.join(os.path.dirname(output_png_path), rise_settle_plots_subdir_name)
    if not os.path.exists(rise_settle_plots_subdir_path):
        os.makedirs(rise_settle_plots_subdir_path)

    results_df = pd.DataFrame(columns=[
        "Name",
        "Ppoc Settling Time (sec)",
        "Qpoc Settling Time (sec)",
        "Vpoc Settling TIme (sec)",
        "Ppoc Rise Time (sec)",
        "Qpoc Rise Time (sec)",
        "Vpoc Rise Time (sec)",
        ])

    # Collect Perr, Qerr, Verr signals for plotting
    perr_mw_signals = []
    qerr_mvar_signals = []
    verr_adj_pu_signals = []

    for i in tqdm(range(len(psout_paths)), desc="Voltage Disturbance Analysis"):
        psout_path = psout_paths[i]
        json_path = psout_path.split(extension)[0] + ".json"

        with open(json_path, 'r') as f:
            spec = json.load(f)
        
        df = out_to_df(psout_path)

        if df_manipulation_fn is not None:
            df = df_manipulation_fn(df)
        
        #print(spec)

    
        df_copy = df
        if not x86:
            init_time_sec = float(spec["substitutions"][init_time_spec_key])
            df_copy = df_copy[df_copy.index > init_time_sec]
            df_copy.index = df_copy.index - init_time_sec
        df = df_copy

        if "Readable_Name" in spec:
            if spec["Readable_Name"] is not None:
                simulation_name = spec["Readable_Name"]
            else:
                simulation_name = spec["File_Name"]
        else:
            simulation_name = spec["File_Name"]
           


        #print(df.columns)
        disturbance_cmd = ParsedDslSignal.parse(str(spec[disturbance_command_spec_key])).signal
        assert disturbance_cmd is not None
        step_times = [piece.time_start for piece in disturbance_cmd.pieces]

        for j, step_time in enumerate(step_times):
            if j == len(step_times) - 1:
                step_analysis_df = df[df.index >= step_time]
                step_plot_df = df[df.index >= step_time - pre_step_plot_secs]
                err_plot_df = df[df.index >= step_time - pre_error_plot_secs]
            else:
                step_analysis_df = df[(df.index >= step_time) & (df.index < step_times[j+1])]
                step_plot_df = df[(df.index >= step_time - pre_step_plot_secs) & (df.index < step_times[j+1])]
                err_plot_df = df[(df.index >= step_time - pre_error_plot_secs) & (df.index < step_times[j+1])]

            # Align the disturbances at 0 sec for plotting
            step_analysis_df.index = step_analysis_df.index - step_time
            step_plot_df.index = step_plot_df.index - step_time
            err_plot_df.index = err_plot_df.index - step_time

            p_results : StepAnalysisResults = analyse_step(series=step_analysis_df[ppoc_mw_signal_name])
            q_results : StepAnalysisResults = analyse_step(series=step_analysis_df[qpoc_mvar_signal_name])
            v_results : StepAnalysisResults = analyse_step(series=step_analysis_df[vpoc_pu_signal_name])

            # Prepare tiles and scenario meta-data
            print(simulation_name)
            scenario_basename = simulation_name
            rise_settle_filepath = os.path.join(rise_settle_plots_subdir_path, f"{scenario_basename}_Step_{j+1}.png")
            if len(step_times) > 1:
                rise_settle_plot_title = spec[rise_settle_title_spec_key]
            else:
                rise_settle_plot_title = f"{spec[rise_settle_title_spec_key]} Step {j+1}"

            produce_rise_settle_plot_pqv(
                    title=rise_settle_plot_title,
                    output_png_path=rise_settle_filepath,
                    subtitle=None,
                    ppoc_mw_series=step_plot_df[ppoc_mw_signal_name],
                    qpoc_mvar_series=step_plot_df[qpoc_mvar_signal_name],
                    vpoc_pu_series=step_plot_df[vpoc_pu_signal_name],
                    p_results=p_results,
                    q_results=q_results,
                    v_results=v_results,
                    )

            perr_mw_signals.append(err_plot_df[ppoc_mw_signal_name])
            qerr_mvar_signals.append(err_plot_df[qpoc_mvar_signal_name])
            verr_adj_pu_signals.append(err_plot_df[vpoc_pu_signal_name])

            new_row = {
                    "Name": scenario_basename,
                    "Ppoc Settling Time (sec)": p_results.settling_time_results.settling_time_sec,
                    "Qpoc Settling Time (sec)": q_results.settling_time_results.settling_time_sec,
                    "Vpoc Settling TIme (sec)": v_results.settling_time_results.settling_time_sec,
                    "Qpoc Settling Time Lower Limit": q_results.settling_time_results.lower_limit,
                    "Qpoc Settling Time Upper Limit": q_results.settling_time_results.upper_limit,
                    "Ppoc Rise Time (sec)": p_results.rise_time_results.rise_time_sec,
                    "Qpoc Rise Time (sec)": q_results.rise_time_results.rise_time_sec,
                    "Vpoc Rise Time (sec)": v_results.rise_time_results.rise_time_sec,
                }

            results_df = pd.concat([results_df, pd.DataFrame([new_row])], ignore_index=True)

    produce_disturbance_tracking_plot_pqv(
            output_png_path=output_png_path,
            title="Voltage Disturbance Tracking Plot",
            results_df=results_df,
            perr_mw_signals=perr_mw_signals,
            qerr_mvar_signals=qerr_mvar_signals,
            verr_adj_pu_signals=verr_adj_pu_signals,
            )

    results_df.to_csv(output_csv_path, index=False)








        


        


    
