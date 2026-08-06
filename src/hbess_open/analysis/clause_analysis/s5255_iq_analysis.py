import os
import json
import pandas as pd
from typing import List, Tuple, Optional, Callable
from hbess_open.utils.progress import tqdm

from hbess_open.analysis.gridlink.boxplots import make_boxplot
from hbess_open.analysis.gridlink.characteristic_overlays import make_characteristic_overlay
from hbess_open.io.result_data import SimulationOut as Out, companion_path, initialisation_seconds
from hbess_open.io.signal_dsl import ParsedDslSignal

import matplotlib.pyplot as plt


def produce_s5255_iq_outputs(
        fault_psout_paths : Optional[List[str]],
        tov_psout_paths : Optional[List[str]],
        groupby_str_for_plot_titles: str,
        output_png_path: str,
        output_csv_path: str,
        diqdv_characteristic_points : List[Tuple[float, float]],
        init_time_spec_key : str,
        fault_timing_signal_command_spec_key : Optional[str],
        tov_timing_signal_command_spec_key : Optional[str],
        iq_pos_seq_signal_name : str,
        iq_neg_seq_signal_name : str,
        v_signal_name : str,
        saturation_current_signal_name : str,
        included_voltage_ranges : List[List],
        gps_voltage_thresholds: Optional[List] = None,
        y_label : str = u'Change in Reactive Current, Δ$I_{q}$ (pu)',
        x_label : str = u'Point of Connection Voltage, $V_{fault,settled}$ (pu)',
        title : str = "Reactive Current Injection",
        df_manipulation_fn : Optional[Callable] = None,
        x86 : bool = True,
        ):
    
    # This allows the plotter to be run with only TOV or only Faults
    study_types = []
    if fault_psout_paths is not None and len(fault_psout_paths) > 0:
        study_types.append("Faults")
    if tov_psout_paths is not None and len(tov_psout_paths) > 0:
        study_types.append("TOV")

    results_df = pd.DataFrame(columns=[
        "Name",
        "Study Type",
        "Fault No",
        "Initial pos seq iq (pu)",
        "Initial neg seq iq (pu)",
        "Initial V (pu)",
        "Last iq (pu)",
        "Last V (pu)",
        "Last Saturation Point Current (pu)",
        "Saturated",
        "Grouped By",
        "Delta iq pos seq (pu)",
        "Delta iq neg seq (pu)",
        "ABS(Delta neq2pos seq iq)",
        "Delta V (pu)",
        "Voltage threshold",
        'Delta V (from threshold)',
        "diq over dv"
    ])

    if groupby_str_for_plot_titles is not None:
        title_suffix = f" ({groupby_str_for_plot_titles})"
    else:
        title_suffix = ""

    print(study_types)
    for study_type in study_types:
        psout_paths = fault_psout_paths if study_type == "Faults" else tov_psout_paths
        assert psout_paths is not None

        command_spec_key = fault_timing_signal_command_spec_key if study_type == "Faults" else tov_timing_signal_command_spec_key

        for i in tqdm(range(len(psout_paths)), desc=f"diq/dV studies ({study_type})"):
            psout_path = psout_paths[i]
            json_path = companion_path(psout_path, ".json")

            with open(json_path, 'r') as f:
                spec = json.load(f)

        
            df = Out(psout_path).to_df()

            if df_manipulation_fn is not None:
                df = df_manipulation_fn(df)

            if "Readable_Name" in spec:
                simulation_name = spec["Readable_Name"]
            else:
                simulation_name = spec["File_Name"]

            df_copy = df
            if not x86:
                init_time_sec = initialisation_seconds(spec, init_time_spec_key)
                df_copy = df_copy[df_copy.index > init_time_sec]
                df_copy.index = df_copy.index - init_time_sec
            df = df_copy

            timing_cmd = ParsedDslSignal.parse(spec[command_spec_key]).signal
            if timing_cmd is None:
                raise ValueError("Could not parse {} for {}".format(command_spec_key, simulation_name))
            prefault_times = [piece.time_start - 0.01 for piece in timing_cmd.pieces if piece.target==1.0]
            settled_times = [piece.time_start - 0.01 for piece in timing_cmd.pieces if piece.target==0.0]

            if len(prefault_times) != len(settled_times):
                raise ValueError("Prefault times does not have the same number of elements as settled_times")

            for j, (prefault_time, settled_time) in enumerate(zip(prefault_times, settled_times)):
                prefault_df = df[df.index < prefault_time]
                settled_df = df[df.index < settled_time]
                if prefault_df.empty or settled_df.empty:
                    raise ValueError("No samples available around disturbance {} in {}".format(j + 1, simulation_name))
                has_negative_sequence = iq_neg_seq_signal_name not in {None, "", "NA"} and iq_neg_seq_signal_name in df.columns
                initial_negative = prefault_df[iq_neg_seq_signal_name].iloc[-1] if has_negative_sequence else 0.0
                final_negative = settled_df[iq_neg_seq_signal_name].iloc[-1] if has_negative_sequence else 0.0
                new_row = {
                        "Name": simulation_name,
                        "Study Type": study_type,
                        "Fault No": j+1,
                        "Initial pos seq iq (pu)": prefault_df[iq_pos_seq_signal_name].iloc[-1],
                        "Initial neg seq iq (pu)": initial_negative,
                        "Initial V (pu)": prefault_df[v_signal_name].iloc[-1],
                        "Last pos seq iq (pu)": settled_df[iq_pos_seq_signal_name].iloc[-1],
                        "Last neg seq iq (pu)": final_negative,
                        "Last V (pu)": settled_df[v_signal_name].iloc[-1],
                        "Last Saturation Point Current (pu)": settled_df[saturation_current_signal_name].iloc[-1],
                    }
                results_df = pd.concat([results_df, pd.DataFrame([new_row])], ignore_index=True)
    #print(results_df)
    results_df["Grouped By"]=title_suffix
    results_df["Delta iq pos seq (pu)"] = results_df["Last pos seq iq (pu)"] - results_df["Initial pos seq iq (pu)"]
    results_df["Delta iq neg seq (pu)"] = results_df["Last neg seq iq (pu)"] - results_df["Initial neg seq iq (pu)"]
    results_df["ABS(Delta neq2pos seq iq)"] = results_df["Delta iq neg seq (pu)"].abs()/results_df["Delta iq pos seq (pu)"].abs()
    results_df["Delta V (pu)"] = results_df["Last V (pu)"] - results_df["Initial V (pu)"]
    results_df["Saturated"] = (results_df["Last Saturation Point Current (pu)"] >= 1.0) | (results_df["Last Saturation Point Current (pu)"] <= -1.0)

    #results_df["Included By Voltage Range"] = results_df["Last V (pu)"]

    # def is_included(v):
    #     return any(min_voltage <= v <= max_voltage for min_voltage, max_voltage in included_voltage_ranges)

    # results_df["Included By Voltage Range"] = results_df["Last V (pu)"].apply(is_included)

    if gps_voltage_thresholds is not None:

        results_df.loc[results_df['Study Type'] == 'TOV', 'Voltage threshold'] = max(gps_voltage_thresholds)
        results_df.loc[results_df['Study Type'] == 'Faults', 'Voltage threshold'] = min(gps_voltage_thresholds)
        results_df['fromthresh'] = results_df['Voltage threshold'] - results_df['Last V (pu)']
        results_df.loc[(results_df['fromthresh'] > 0) & (results_df['Study Type'] == 'Faults'), "Included By Voltage Range"] = True
        results_df.loc[(results_df['fromthresh'] < 0) & (results_df['Study Type'] == 'Faults'), "Included By Voltage Range"] = False
        results_df.loc[(results_df['fromthresh'] > 0) & (results_df['Study Type'] == 'TOV'), "Included By Voltage Range"] = False
        results_df.loc[(results_df['fromthresh'] < 0) & (results_df['Study Type'] == 'TOV'), "Included By Voltage Range"] = True
    
    else:
        results_df.loc[results_df['Study Type'] == 'TOV', 'Voltage threshold'] = included_voltage_ranges[1][0]
        results_df.loc[results_df['Study Type'] == 'Faults', 'Voltage threshold'] = included_voltage_ranges[0][1]
        results_df['fromthresh'] = results_df['Voltage threshold'] - results_df['Last V (pu)']
        results_df.loc[(results_df['fromthresh'] > 0) & (results_df['Study Type'] == 'Faults'), "Included By Voltage Range"] = True
        results_df.loc[(results_df['fromthresh'] < 0) & (results_df['Study Type'] == 'Faults'), "Included By Voltage Range"] = False
        results_df.loc[(results_df['fromthresh'] > 0) & (results_df['Study Type'] == 'TOV'), "Included By Voltage Range"] = False
        results_df.loc[(results_df['fromthresh'] < 0) & (results_df['Study Type'] == 'TOV'), "Included By Voltage Range"] = True


    results_df['Delta V (from threshold)'] = results_df['Voltage threshold'] - results_df['Last V (pu)']
    results_df['diq over dv'] = results_df['Delta iq pos seq (pu)'] / abs(results_df['Delta V (from threshold)'])
    results_df['diq neg over dv'] = results_df['Delta iq neg seq (pu)'] / abs(results_df['Delta V (from threshold)'])


    results_df.to_csv(output_csv_path, index=False)

    # failed_faults_csv_path=os.path.join(output_csv_folder, "failed_faults.csv")
    # failed_tov_csv_path=os.path.join(output_csv_folder, "failed_tov.csv")

    # failed_df = results_df[results_df["Included By Voltage Range"] == True]
    # failed_df = failed_df[failed_df["Saturated"] == False]

    # failed_faults = failed_df[failed_df['diq over dv'] <= 4]
    # failed_faults = failed_faults[failed_faults["Delta V (pu)"] < 0]

    # failed_tov = failed_df[failed_df['diq over dv'] > -6]
    # failed_tov = failed_tov[failed_tov["Delta V (pu)"] > 0]

    # failed_faults.to_csv(failed_faults_csv_path, index=False)
    # failed_tov.to_csv(failed_tov_csv_path, index=False)

    # Prune the non-FRT voltage range after saving the CSV
    results_df = results_df[results_df["Included By Voltage Range"] == True]

    make_characteristic_overlay(
        output_path=output_png_path,
        points=list(results_df.loc[results_df["Saturated"] == False, ["Last V (pu)", "Delta iq pos seq (pu)"]].itertuples(index=False, name=None)),
        saturated_points=list(results_df.loc[results_df["Saturated"] == True, ["Last V (pu)", "Delta iq pos seq (pu)"]].itertuples(index=False, name=None)),
        characteristic_points=diqdv_characteristic_points,
        title=title+title_suffix,
        y_label=y_label,
        x_label=x_label,
        points_colour='red',
        characteristic_colour='black',
        saturated_points_label = 'Above Maximum Continuous Current',
        saturated_points_colour = 'grey',
        points_label = "Measured Values",
        characteristic_label = "Access Standard",
        points_additional_args={"marker": "x"},
        saturated_points_additional_args={"marker": "o"},
        characteristic_additional_args={"linestyle": '--'},
        )    

    # make_boxplot(
    #     groupby_str_for_plot_title=groupby_str_for_plot_titles,
    #     figure_title="Iq Sequence Contributions",
    #     output_png_path=os.path.join(os.path.dirname(output_png_path),f"s5255 Iq Sequence Contributions {title_suffix}.png"),
    #     data=[
    #         results_df.loc[results_df["Saturated"] == True, "ABS(Delta neq2pos seq iq)"],
    #         results_df.loc[results_df["Saturated"] == False, "ABS(Delta neq2pos seq iq)"],
    #         ],
    #     xtick_labels=[
    #         ">= Max Cont. Current",
    #         "< Max Cont. Current"
    #             ],
    #     ylabel_title=r"$ABS(\frac{\Delta I_{q,neg}}{\Delta I_{q,pos}})$"
    # )





























