import os
import json
import pandas as pd
import numpy as np
from typing import List, Callable, Optional
from hbess_open.utils.progress import tqdm

from hbess_open.io.result_data import companion_path, initialisation_seconds, result_to_df
from hbess_open.io.signal_dsl import ParsedDslSignal


from dataclasses import dataclass


@dataclass
class FREQ_BAND:
    upper: float
    lower: float

@dataclass
class SYSTEM_STATE:
    primary_freq_control_band : FREQ_BAND
    norm_operating_freq_band : FREQ_BAND
    norm_operating_freq_exc_band : FREQ_BAND
    operating_freq_tolerance_band : FREQ_BAND
    extreme_freq_exc_tolerance_limit: FREQ_BAND

normal_mainland_bands = SYSTEM_STATE(
    primary_freq_control_band=FREQ_BAND(
        upper=50.015,
        lower=49.985),
    norm_operating_freq_band=FREQ_BAND(
        upper=50.15,
        lower=49.85),
    norm_operating_freq_exc_band=FREQ_BAND(
        upper=50.25,
        lower=49.75),
    operating_freq_tolerance_band=FREQ_BAND(
        upper=51.0,
        lower=49.0),
    extreme_freq_exc_tolerance_limit=FREQ_BAND(
        upper=52.0,
        lower=47.0),
    )

def is_nan(value):
    return isinstance(value, float) and np.isnan(value)

def p_reduction_table(
        psout_paths : List[str],
        freq_channel_key: str,
        active_power_channel_key: str,
        output_csv_path: str,
        p_ramp_down_threshold: float,
        freq_init_ramp_down: float,
        freq_complete_ramp_down: float, #= normal_mainland_bands.extreme_freq_exc_tolerance_limit.upper,
        df_manipulation_fn : Optional[Callable] = None,
        pmax: Optional[int] = None,
        Discharge_Cases_only:Optional[bool]=None,
        x86 : bool = True,
    ):
    results_df = pd.DataFrame(columns=[
            "Name",
            # "Lower Freq Band Time (s)": round(t_lower_limit,2),
            "Grid SCR",
            "Grid X/R",
            "Frequency Excursion (Hz)",
            "Frequency Excursion Time (s)",
            "Pre-disturbance Active Power (MW)",
            "Active Power Threshold (MW)",
            "Active Power Threshold Time (s)",
            "Active Power Reduction Time (s)",
            "Active Power Reduced within 3s",
        ])

            
    
    # for i in tqdm(range(len(psout_paths)), desc="Active Power Reduction Analysis"):
    for i in range(len(psout_paths)):
        psout_path = psout_paths[i]
        json_path = companion_path(psout_path, ".json")

        with open(json_path, 'r') as f:
            spec = json.load(f)

        for dir in [os.path.dirname(output_csv_path)]:
            if not os.path.exists(dir):
                os.makedirs(dir)
                
        TIME_SHIFT_SEC = 0.01
        

        if "Readable_Name" in spec:
            if is_nan(spec["Readable_Name"]):
                simulation_name = spec["File_Name"]
            
            else:
                simulation_name = spec["Readable_Name"]
                if simulation_name is None:
                    simulation_name = spec["File_Name"]
        
        else:
            simulation_name = spec["File_Name"]
         
   

        filename = simulation_name
        df = result_to_df(psout_path)

        if df_manipulation_fn is not None:
            df = df_manipulation_fn(df)

        df_copy = df

        if not x86:
            init_time_sec = initialisation_seconds(spec)
            df_copy = df_copy[df_copy.index > init_time_sec]
            df_copy.index = df_copy.index - init_time_sec

        df = df_copy
        df_crg_copy = df.copy()
        

        p_init = df[active_power_channel_key].iloc[0]
      
        f_init = df[freq_channel_key].iloc[0]
        p_threshold = p_ramp_down_threshold*p_init
        p_threshold_neg = p_init + p_threshold   #for charging cases 
        AT_MAX_CHARGE = False # Default, assume that the inital active power is not at max, will become True if it is at max charge 
        buffer = 0.01
        if pmax is not None:
            if p_init <= -pmax + buffer:  #added a buffer as sometimes measured voltage isn't always at -pmax, can be just below it 
                AT_MAX_CHARGE = True
               

            if p_threshold_neg <= -pmax:
                p_threshold_neg = -pmax
            
        else:
            if p_threshold_neg <= -60:   #default pmax for project, specific for cgbess
                p_threshold_neg = -60
            if p_init <= -60:
                AT_MAX_CHARGE = True

        t_lower_limit = df[df[freq_channel_key]>=freq_init_ramp_down].index[0] if len(df[df[freq_channel_key]>=freq_init_ramp_down])>0 else np.nan
        t_upper_limit = df[df[freq_channel_key]>=freq_complete_ramp_down].index[0] if len(df[df[freq_channel_key]>=freq_complete_ramp_down])>0 else np.nan
        if p_init < 0:
            t_p_threshold = df[df[active_power_channel_key]<=p_threshold_neg].index[0] if len(df[df[active_power_channel_key]<=p_threshold_neg])>0 else np.nan
            p_final_mw = df[df[active_power_channel_key]<=p_threshold_neg][active_power_channel_key].iloc[0] if len(df[df[active_power_channel_key]<=p_threshold_neg])>0 else np.nan
            if AT_MAX_CHARGE:
                df_crg_copy = df_crg_copy[df_crg_copy.index >= t_upper_limit]  
                t_p_threshold = df_crg_copy[df_crg_copy[active_power_channel_key]<=p_threshold_neg].index[0]  if len(df_crg_copy[df_crg_copy[active_power_channel_key]<=p_threshold_neg])>0 else np.nan
                
                print(t_p_threshold)
        else:
            t_p_threshold = df[df[active_power_channel_key]<=p_threshold].index[0] if len(df[df[active_power_channel_key]<=p_threshold])>0 else np.nan
            p_final_mw = df[df[active_power_channel_key]<=p_threshold][active_power_channel_key].iloc[0] if len(df[df[active_power_channel_key]<=p_threshold])>0 else np.nan

        if t_p_threshold-t_upper_limit < 3:
            is_compliant = True
        else:
            is_compliant = False
        
        if Discharge_Cases_only is not None and Discharge_Cases_only:
            if p_init > 0:
                new_row = {
                    "Name": simulation_name,
                    "Grid SCR": spec["Grid_SCR"],
                    "Grid X/R": spec["Grid_X2R_sig"],
                    # "Lower Freq Band Time (s)": round(t_lower_limit,2),
                    "Frequency Excursion (Hz)": round(freq_complete_ramp_down,2),
                    "Frequency Excursion Time (s)": round(t_upper_limit,2),

                    "Pre-disturbance Active Power (MW)": round(p_init,2),
                    "Active Power Threshold (MW)": round(p_final_mw,2),
                    "Active Power Threshold Time (s)": round(t_p_threshold,2),
                    "Active Power Reduction Time (s)": round(t_p_threshold-t_upper_limit,2),
                    "Active Power Reduced within 3s": is_compliant,
                    # "Lower Frequency (Hz)": round(freq_init_ramp_down,2),
                
                }
                results_df = pd.concat([results_df, pd.DataFrame([new_row])], ignore_index=True)
        else:
            new_row = {
                "Name": simulation_name,
                "Grid SCR": spec["Grid_SCR"],
                "Grid X/R": spec["Grid_X2R_sig"],
                # "Lower Freq Band Time (s)": round(t_lower_limit,2),
                "Frequency Excursion (Hz)": round(freq_complete_ramp_down,2),
                "Frequency Excursion Time (s)": round(t_upper_limit,2),

                "Pre-disturbance Active Power (MW)": round(p_init,2),
                "Active Power Threshold (MW)": round(p_final_mw,2),
                "Active Power Threshold Time (s)": round(t_p_threshold,2),
                "Active Power Reduction Time (s)": round(t_p_threshold-t_upper_limit,2),
                "Active Power Reduced within 3s": is_compliant,
                # "Lower Frequency (Hz)": round(freq_init_ramp_down,2),
            
            }
            results_df = pd.concat([results_df, pd.DataFrame([new_row])], ignore_index=True)


    results_df.to_csv(output_csv_path)


