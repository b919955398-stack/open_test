import os
import json
import pandas as pd
from typing import List, Dict, Optional, Callable
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from hbess_open.utils.progress import tqdm

from hbess_open.io.result_data import SimulationOut as Out, companion_path, initialisation_seconds
from hbess_open.io.signal_dsl import ParsedDslSignal


def produce_cuo_summary_outputs(
        psout_paths : List[str],
        output_png_path : str,
        output_csv_path : str,
        init_time_spec_key : str,
        vterm_rms_pu_signal_name : str,
        vpoc_pu_command_spec_key : str,
        hvrt_thresholds : List[Dict],
        lvrt_thresholds : List[Dict],
        secs_to_plot_before_step : float = 1.0,
        fill_alpha : float = 0.2,
        legend_item_alpha : float = 0.8,
        df_manipulation_fn : Optional[Callable] = None,
        x86 : bool = True,
        ):
    
    plt.figure(figsize=(10,6))

    sorted_hvrt_thresholds = sorted(hvrt_thresholds, key=lambda x: x["value"])
    sorted_lvrt_thresholds = sorted(lvrt_thresholds, key=lambda x: x["value"], reverse=True)

    signal_lengths = []
    results_df = pd.DataFrame(columns=[
        "Name",
        "Initial Vpoc (pu)",
        "Stepped Voltage (pu)",
        "Most Severe Band",
        "Final Band",
        "Most Severe Undervoltage (pu)",
        "Most Severe Overvoltage (pu)",
        "Final Voltage (pu)",
    ])
    for i in tqdm(range(len(psout_paths)), desc="Reading CUO psout files"):
        psout_path = psout_paths[i]
        json_path = companion_path(psout_path, ".json")

        with open(json_path, 'r') as f:
            spec = json.load(f)
        
        

        if "Readable_Name" in spec:
            simulation_name = spec["Readable_Name"]
        else:
            simulation_name = spec["File_Name"]
    
        print(psout_path)
        df = Out(psout_path).to_df()

        if df_manipulation_fn is not None:
            df = df_manipulation_fn(df)

        df_copy = df
        if not x86:
            init_time_sec = initialisation_seconds(spec, init_time_spec_key)
            df_copy = df_copy[df_copy.index > init_time_sec]
            df_copy.index = df_copy.index - init_time_sec
        df = df_copy

        vpoc_cmd = ParsedDslSignal.parse(spec[vpoc_pu_command_spec_key]).signal
        assert vpoc_cmd is not None
        step_time = vpoc_cmd.pieces[0].time_start

        reduced_df = df[df.index > step_time - secs_to_plot_before_step]
        reduced_df.index = reduced_df.index - step_time + secs_to_plot_before_step        
        signal_lengths.append(reduced_df.index[-1])

        plt.plot(reduced_df.index, reduced_df[vterm_rms_pu_signal_name], color='black')

        most_severe_undervoltage = min(reduced_df[vterm_rms_pu_signal_name])
        most_severe_overvoltage = max(reduced_df[vterm_rms_pu_signal_name])
        final_voltage = reduced_df[vterm_rms_pu_signal_name].iloc[-1]

        # Identify the worst case temporary and permanent excursions
        most_severe_band = 'Continuous'
        final_band = 'Continuous'
        for threshold in lvrt_thresholds:
            if most_severe_undervoltage < threshold["value"]:
                most_severe_band = f'{threshold["withstand_sec"]} sec'
            if final_voltage < threshold["value"]:
                final_band = f'{threshold["withstand_sec"]} sec'
        for threshold in hvrt_thresholds:
            if most_severe_overvoltage > threshold["value"]:
                most_severe_band = f'{threshold["withstand_sec"]} sec'
            if final_voltage > threshold["value"]:
                final_band = f'{threshold["withstand_sec"]} sec'

        new_row = {
                "Name": simulation_name,
                "Initial Vpoc (pu)": vpoc_cmd.initial_value,
                "Stepped Voltage (pu)": vpoc_cmd.pieces[0].target,
                "Most Severe Band": most_severe_band,
                "Final Band": final_band,
                "Most Severe Undervoltage (pu)": most_severe_undervoltage,
                "Most Severe Overvoltage (pu)": most_severe_overvoltage,
                "Final Voltage (pu)": final_voltage,
                }

        results_df = pd.concat([results_df, pd.DataFrame([new_row])], ignore_index=True)


    """ HVRT """
    for i in range(len(sorted_hvrt_thresholds)):
        threshold = sorted_hvrt_thresholds[i]

        plt.axhline(
            y=threshold['value'],
            color=threshold['colour'],
            linestyle='-',
        )

        not_last = i < len(sorted_hvrt_thresholds) - 1 
        if not_last:
            fill_between_max = sorted_hvrt_thresholds[i+1]['value']
        else:
            fill_between_max = 100

        plt.axhspan(threshold['value'], fill_between_max, facecolor=threshold['colour'], alpha=fill_alpha)

    """ LVRT """
    for i in range(len(sorted_lvrt_thresholds)):
        threshold = sorted_lvrt_thresholds[i]

        plt.axhline(
            y=threshold['value'],
            color=threshold['colour'],
            linestyle='-',
        )

        not_last = i < len(sorted_lvrt_thresholds) - 1 
        if not_last:
            fill_between_min = sorted_lvrt_thresholds[i+1]['value']
        else:
            fill_between_min = 0.0

        plt.axhspan(fill_between_min, threshold['value'], facecolor=threshold['colour'], alpha=fill_alpha)

    # Create the legend
    all_thresholds = sorted_hvrt_thresholds + sorted_lvrt_thresholds
    withstand_times = {}
    for threshold in all_thresholds:
        withstand_times[threshold['withstand_sec']] = threshold['colour']

    legend_elements = []
    for withstand_sec, colour in sorted(withstand_times.items()):
        legend_elements.append(Patch(
            facecolor=colour,
            label=f"{withstand_sec}sec withstand",
            alpha=legend_item_alpha,
        ))

    plt.title("CUO Steps")
    plt.ylabel('Terminal Voltage (pu)')
    plt.xlabel('Time (s)')
    plt.legend(handles=legend_elements, loc='upper right', framealpha=0.9)
    plt.grid(True)

    plt.xlim(0.0, min(signal_lengths))
    plt.ylim(0.6,1.3)
    #plt.ylim(min(results_df["Most Severe Undervoltage (pu)"]) - 0.2, max(results_df["Most Severe Overvoltage (pu)"]) + 0.05)

    plt.savefig(output_png_path)

    results_df.to_csv(output_csv_path, index=False)

