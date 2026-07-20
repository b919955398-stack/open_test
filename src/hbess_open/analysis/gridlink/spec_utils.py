import json
from pathlib import Path

import pandas as pd
from hbess_open.utils.progress import tqdm



def sort_grouped_paths_by_spec(
        sort_by_spec_key : str,
        group_by_spec_keys : list,
        paths : list[str],
    ) -> dict:

    df_columns = [
        "psout_path",
    ]

    keys_of_interest = [x for x in group_by_spec_keys]
    keys_of_interest.append(sort_by_spec_key)

    unique_keys_of_interest = list(set(keys_of_interest))

    [df_columns.append(x) for x in unique_keys_of_interest]

    results_df = pd.DataFrame(columns=df_columns)
    
    for i in tqdm(range(len(paths)), desc="Preparing Ordered List"):

        psout_path = paths[i]
        json_path = str(Path(psout_path).with_suffix(".json"))

        with open(json_path, 'r') as f:
            spec = json.load(f)    

        new_row = {key: spec[key] for key in unique_keys_of_interest}
        new_row["psout_path"] = psout_path

        results_df = pd.concat([results_df, pd.DataFrame([new_row])], ignore_index=True)


    grouped = results_df.groupby(group_by_spec_keys)
    print(grouped)
    
    grouped_sorted_paths = {}
    for group_name, group_df in grouped:
        sorted_df = group_df.sort_values(sort_by_spec_key)
        grouped_sorted_paths[group_name] = [psout_path for psout_path in sorted_df["psout_path"]]

    return grouped_sorted_paths
