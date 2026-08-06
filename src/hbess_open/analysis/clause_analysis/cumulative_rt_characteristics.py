import os
import glob
import json
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from typing import List, Tuple, Optional, Dict, Callable
from hbess_open.utils.progress import tqdm

from hbess_open.analysis.gridlink.characteristic_overlays import make_characteristic_overlay
from hbess_open.io.result_data import SimulationOut as Out, initialisation_seconds
from hbess_open.io.signal_dsl import ParsedDslSignal
import pickle


def produce_cumulative_ride_through_outputs(
        psout_paths : List[str],
        output_png_path : str,
        output_csv_path : str,
        init_time_spec_key : str,
        step_size : float,
        high_characteristic_points : List[Tuple[float, float]],
        low_characteristic_points : List[Tuple[float, float]],
        measurement_signal_name : str,
        error_signal_name : Optional[str] = None,
        y_label : str = "Withstand",
        x_label : str = "Cumulative withstand time (sec)",
        title : str = "Withstand",
        characteristic_additional_args : Optional[Dict] = None,
        study_name_for_progress_bar : str = "Cumulative ride through",
        df_manipulation_fn : Optional[Callable] = None,
        x_axis_min : Optional[float] = None,
        x_axis_max : Optional[float] = None,
        x86 : bool = True,

        ):
    
    # Collect data
    low_x_char_points, low_y_char_points = zip(*low_characteristic_points)
    high_x_char_points, high_y_char_points = zip(*high_characteristic_points)

    low_study_range = np.arange(min(low_y_char_points), max(low_y_char_points), step_size)
    high_study_range = np.arange(min(high_y_char_points), max(high_y_char_points), step_size)

    results_df = pd.DataFrame(columns=["Name"] + list(low_study_range) + list(high_study_range))
    error_times = []
    low_results_series = []
    high_results_series = []

    for i in tqdm(range(len(psout_paths)), desc=study_name_for_progress_bar):
        psout_path = psout_paths[i]
        extension = "."+psout_path.split(".")[-1]
        json_path = psout_path.split(extension)[0] + ".json"

        with open(json_path, 'r') as f:
            spec = json.load(f)

        if "Readable_Name" in spec:
            simulation_name = spec["Readable_Name"]
        else:
            simulation_name = spec["File_Name"]

        if extension == ".pkl":
            df = pd.read_pickle(psout_path)
        else:
            df = Out(psout_path).to_df()

        if df_manipulation_fn is not None:
            df = df_manipulation_fn(df)

        df_copy = df
        if not x86:
            init_time_sec = initialisation_seconds(spec, init_time_spec_key)
            df_copy = df_copy[df_copy.index > init_time_sec]
            df_copy.index = df_copy.index - init_time_sec
        df = df_copy

        df_step_size = float(df.index[1]) - float(df.index[0])

        new_row = {
                "Name": simulation_name,
                }

        low_cumulative_time_points = []
        high_cumulative_time_points = []
        #print(max(low_study_range))

        for k,j in enumerate(low_study_range):
            if k == len(low_study_range)-1:
                adjusted_limit = j*1.01
            else:
                adjusted_limit = j
            filtered_df = df[df[measurement_signal_name] <= adjusted_limit]
            cumulative_time = len(filtered_df) * df_step_size
            new_row[j] = cumulative_time
            low_cumulative_time_points.append((cumulative_time, j))

        for j in high_study_range:
            if j == len(high_study_range)-1:
                adjusted_limit = j*0.99
            else:
                adjusted_limit = j
            filtered_df = df[df[measurement_signal_name] >= adjusted_limit]
            cumulative_time = len(filtered_df) * df_step_size
            new_row[j] = cumulative_time
            high_cumulative_time_points.append((cumulative_time, j))

        if error_signal_name is not None:
            error_times_df = df[df[error_signal_name] > 0.5]
            if len(error_times_df) > 0:
                error_times.append(error_times_df.index[0])
            else:
                error_times.append(None)
        else:
            error_times.append(None)

        results_df = pd.concat([results_df, pd.DataFrame([new_row])], ignore_index=True)
        high_cumulative_time_points = sorted(high_cumulative_time_points, key=lambda item: (item[0], -item[1]))
        low_cumulative_time_points = sorted(low_cumulative_time_points, key=lambda item: (item[0], item[1]))
        #print(low_cumulative_time_points[-1])

        low_results_series.append(low_cumulative_time_points)
        high_results_series.append(high_cumulative_time_points)


        #print(high_cumulative_time_points)


    results_df.to_csv(output_csv_path, index=False)

    plt.clf()
    plt.close()

    characteristic_extra_args = {} if characteristic_additional_args is None else characteristic_additional_args
    plt.semilogx(
        low_x_char_points,
        low_y_char_points,
        label="Access Standard",
        color='black',
        linestyle='--',
        **characteristic_extra_args,
    )

    plt.semilogx(
        high_x_char_points,
        high_y_char_points,
        color='black',
        linestyle='--',
        **characteristic_extra_args,
    )

    err_added_to_legend = False
    ok_added_to_legend = False
    for results_series in [low_results_series, high_results_series]:
        for i, points_list in enumerate(results_series):
            sorted_points_list = sorted(points_list, key=lambda x: x[0])
            if error_times[i] is not None:
                errored_points = [point for point in sorted_points_list if point[0] >= error_times[i]]
                ok_points = [point for point in sorted_points_list if point[0] < error_times[i]]
            else:
                errored_points = []
                ok_points = sorted_points_list

            # Filter out 0 time points - they are uninteresting
            errored_points = [(t, v) for t, v in errored_points if t != 0.0]
            ok_points = [(t, v) for t, v in ok_points if t != 0.0]

            # If we don't add a point close to t=0, the first point may be half way along the x axis
            if len(ok_points) > 0:
                ok_points.insert(0, (0.0, ok_points[0][1]))

            # If we have an error, there will be a gap between the ok and error lines
            if len(errored_points) > 0:
                ok_points.append(errored_points[0])


            if len(errored_points) > 0:
                err_label = "Tripped" if err_added_to_legend is False else None
                x_err, y_err = zip(*errored_points)
                plt.semilogx(x_err, y_err, marker='', color='red', label=err_label)
                err_added_to_legend = True

            if len(ok_points) > 0:
                ok_label = "Results" if ok_added_to_legend is False else None
                x_ok, y_ok = zip(*ok_points)
                plt.semilogx(x_ok, y_ok, marker='', color='#96b23d', label=ok_label)
                ok_added_to_legend = True


    plt.title(title)
    plt.xlabel(x_label)
    plt.ylabel(y_label)
    plt.legend()
    plt.xlim(x_axis_min, x_axis_max)
    plt.savefig(output_png_path)
    plt.clf()
    plt.close()

    # plt.show()
