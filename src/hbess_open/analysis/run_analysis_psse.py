import os
import sys
import glob
import warnings
import pandas as pd
import numpy as np
from typing import List, Optional, Callable
import json
import traceback
import shutil

from hbess_open.analysis.clause_analysis.cumulative_rt_characteristics import produce_cumulative_ride_through_outputs
from hbess_open.analysis.clause_analysis.s52511_dpdf_analysis import produce_s52511_dpdf_outputs
from hbess_open.analysis.clause_analysis.s52513_disturbance_analysis import produce_disturbance_analysis_outputs
from hbess_open.analysis.clause_analysis.s52513_vdroop_analysis import produce_vdroop_outputs
from hbess_open.analysis.clause_analysis.s5254_cuo_analysis import produce_cuo_summary_outputs
from hbess_open.analysis.clause_analysis.s5255_iq_analysis import produce_s5255_iq_outputs
from hbess_open.analysis.clause_analysis.s5255_rise_settle_recovery_analysis import produce_s5255_rise_settle_recovery_curve
from hbess_open.analysis.clause_analysis.s5258_disturbance_analysis import p_reduction_table
from hbess_open.plotting.process_and_calc_psse import pre_process_dataframe


warnings.simplefilter(action='ignore', category=pd.errors.PerformanceWarning)
warnings.simplefilter(action='ignore', category=FutureWarning)



def run_analysis_psse(
        x86:bool,
        extension: str,
        ANALYSIS_TO_RUN: list,
        DPDF_CHARACTERISTIC_POINTS,
        VDROOP_CHARACTERISTIC_POINTS,
        HVRT_THRESHOLDS,
        LVRT_THRESHOLDS,
        CSR_INPUTS_DIR,
        OUTPUTS_DIR,
        ):


    if not x86:
        raise NotImplementedError("run_analysis_psse is the PSS/E post-processing entry point")
    if extension.lower() != ".out":
        raise ValueError("PSS/E analysis expects extension='.out'; adjacent CSV files are read automatically")

    # Spec keys
    INIT_TIME_SPEC_KEY = "TIME_Full_Init_Time_sec" #no
    FSLACK_HZ_COMMAND_SPEC_KEY = "Fslack_Hz_sig" #no
    VPOC_PU_COMMAND_SPEC_KEY = "Vpoc_pu_sig" #done
    VSLACK_PU_COMMAND_SPEC_KEY_VGRID = "Vslack_pu_psse" #done   #added by cs 8/04
    VSLACK_PU_COMMAND_SPEC_KEY_CUO = "Vpoc_disturbance_pu_sig"   #added by cs 8/04
    VSLACK_PU_COMMAND_SPEC_KEY_PF = "PFref_sig"


    VREF_PU_COMMAND_SPEC_KEY = "Vref_pu_sig" #done
    QREF_PU_COMMAND_SPEC_KEY = "Qref_MVAr_sig" #no
    PFREF_PU_COMMAND_SPEC_KEY = "PFref_pu_sig" #no

    FAULT_TIMING_SIGNAL_COMMAND_SPEC_KEY = "Fault_Timing_Signal_sig" # done
    TOV_TIMING_SIGNAL_COMMAND_SPEC_KEY="TOV_Timing_Signal_sig" #done
    FAULT_TYPE_COMMAND_SPEC_KEY="Fault_Type_sig" # done
    INV_ERR_MSG_SPEC_KEY = "INV_OPERATION_STATE" #no
    INV_OPERATION_STATE_SPEC_KEY = "INV_ERROR_REGISTER" #no
    GRID_FAULT_LEVEL_SPEC_KEY = "Grid_FL_MVA_sig" #done
    ORT_OSC_FREQ_KEY="Vslack_osc_Hz_sig" #no
    ORT_OSC_AMP_KEY="Vslack_osc_amplitude_sig" #no
    ORT_OSC_ANGLE_KEY="Vslack_osc_phase_deg_sig" #no
    # Signals
    PREF_MW_SIGNAL_NAME = "PREF_MW"
    VTERM_RMS_PU_SIGNAL_NAME = "V_HYBESS_PU"
    QREF_MVAR_SIGNAL_NAME = "PwrRtSpntTot_MVAr"
    PPOC_MW_SIGNAL_NAME = "PPOC_MW"
    # ``POC_F_PU`` is the raw PSS/E per-unit frequency deviation. The supplied
    # preprocessor exposes the physical-Hz signal used by the clause metrics.
    FPOC_HZ_SIGNAL_NAME = "Hz_POI"
    QPOC_MVAR_SIGNAL_NAME = "QPOC_MVAR"
    VPOC_RMS_PU_SIGNAL_NAME = "V_POC_PU"
    INV1_IQ_POS_SIGNAL_NAME = "INV1_Iq_PU"

    POC_IQ_POS_SIGNAL_NAME = "POC_Iq_PU"
    POC_IRMS_PU_SIGNAL_NAME = "Irms_HV_pu_max_cont"
    INV1_VTERM_RMS_PU_SIGNAL_NAME = "V_HYBESS_PU"

 
    VREF_PU_SIGNAL_NAME = "V_POC_REF_PU"
    PERR_MW_SIGNAL_NAME = "poc_p_err_MW"
    QERR_MVAR_SIGNAL_NAME = "poc_q_err_MVAr"
    VERR_ADJ_PU_SIGNAL_NAME = "poc_v_err_adj_pu"

    INV_IQ_NEG_SIGNAL_NAME = "Iq_inv_neg_pu"
    POC_IRMS_KA_SIGNAL_NAME = "Irms_HV"
    POC_VRMS_PHA_SIGNAL_NAME="V_hv_rms_phase_A"
    POC_VRMS_PHB_SIGNAL_NAME="V_hv_rms_phase_B"
    POC_VRMS_PHC_SIGNAL_NAME="V_hv_rms_phase_C"
    ERROR_SIGNAL_NAME = "ERROR"
    # Characteristics

    DIQDV_CHARACTERISTIC_POINTS = [(0,1.0),(0.3,1.0),(0.8,0),(1.20,0),(1.7,-1),(2.0,-1.0)] # Voltage @ POC  vs Current injection @ INV from GPS
    DIQDV_INV_CHARACTERISTIC_POINTS = [(0.5,1),(0.685,1.0),(0.85,0),(1.18,0),(1.345,-1),(1.5,-1)]  # Voltage @ INV vs Current Injection @ INV from DYR/Config    

    HFRT_CHARACTERISTIC_POINTS = [(0, 52.001), (600, 52), (600, 50.5001), (800, 50.5)]  #Aligns with GPS
    LFRT_CHARACTERISTIC_POINTS = [(0, 46.999), (120, 47), (120, 47.999), (600, 48), (600, 49.499), (800, 49.5)]    #Aligns with GPS


    HVRT_CHARACTERISTIC_POINTS = [(0, 1.3501), (0.02, 1.35), (0.02, 1.301), (0.2, 1.3), (0.2, 1.2501), (2.0, 1.25), (2.0, 1.201), (20, 1.2), (20, 1.151), (1200, 1.15), (1200, 1.1001), (1500, 1.1)]  #Aligns with GPS
    LVRT_CHARACTERISTIC_POINTS = [(0, 0.699), (2, 0.7), (2, 0.8), (10, 0.8), (10, 0.9), (1500, 0.9)] #Aligns with GPS

    # Constants
    DIQDV_STARTING_VOLTAGE_OV_PU = 1.25 #Updated for GESF
    DIQDV_STARTING_VOLTAGE_UV_PU = 0.8 #Updates for GESF

    DIQDV_INCLUDED_VOLTAGE_RANGES = [[0.4,1],[1.25,1.5]]#[[0.6,DIQDV_STARTING_VOLTAGE_UV_PU], [DIQDV_STARTING_VOLTAGE_OV_PU,1.4]]
    DIQDV_INV_INCLUDED_VOLTAGE_RANGES = [[0.0,1],[1.18,1.3]]
    # To be converted into spec keys when data in pscad
    PMAX_MW = 250.0
    PMIN_MW = 0.0

    PSCAD_FAULT_TYPE_ENUMS = {
        0: "No Fault",
        1: "1PhG",
        2: "1PhG",
        3: "1PhG",
        4: "2PhG",
        5: "2PhG",
        6: "2PhG",
        7: "3PhG",
        8: "PhPh",
        9: "PhPh",
        10: "PhPh",
        11: "3Ph",
        }
    
    PSCAD_HEALTHY_PHASE_ENUMS = {
        0: ["Phase A","Phase B","Phase C"],
        1: ["Phase B", "Phase C"],
        2: ["Phase A", "Phase C"],
        3: ["Phase A","Phase B"],
        4: ["Phase C"],
        5: ["Phase B"],
        6: ["Phase A"],
        7: [],
        8: ["Phase C"],
        9: ["Phase B"],
        10: ["Phase A"],
        11: [],
    }

    errors = []
    if not os.path.exists(OUTPUTS_DIR):
        os.makedirs(OUTPUTS_DIR)


    if "dP/df characteristic" in ANALYSIS_TO_RUN:
        try:
            out_paths = glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR Fgrid Steps") + "/*"+extension)
            filtered_paths = [s for s in out_paths if "52511" in s]
    
            produce_s52511_dpdf_outputs(
                    psout_paths = filtered_paths,
                    output_png_path=os.path.join(OUTPUTS_DIR, "dpdf_characteristic.png"),
                    output_csv_path=os.path.join(OUTPUTS_DIR, "dpdf_results.csv"),
                    init_time_spec_key = INIT_TIME_SPEC_KEY,
                    pref_mw_signal_name=PREF_MW_SIGNAL_NAME,
                    ppoc_mw_signal_name=PPOC_MW_SIGNAL_NAME,
                    fpoc_hz_signal_name=FPOC_HZ_SIGNAL_NAME,
                    fslack_hz_command_spec_key = FSLACK_HZ_COMMAND_SPEC_KEY,
                    dpdf_characteristic_points=DPDF_CHARACTERISTIC_POINTS,
                    df_manipulation_fn=pre_process_dataframe,
                    pmax_mw=PMAX_MW,
                    pmin_mw=PMIN_MW,
                    x86=x86
                    )
        except Exception as e:
            print("Failed on:     dP/df characteristic")
            print(e)
            errors.append(f"dP/df characteristic: {e}")
            traceback.print_exc()
            

    if "CUO" in ANALYSIS_TO_RUN:
        try:
            out_paths = glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR Vgrid Steps") + "/*"+extension)
            filtered_paths = [s for s in out_paths if "CUO" in s]
       
            produce_cuo_summary_outputs(
                    psout_paths = filtered_paths,
                    output_png_path=os.path.join(OUTPUTS_DIR, "cuo_summary.png"),
                    output_csv_path=os.path.join(OUTPUTS_DIR, "cuo_results.csv"),
                    init_time_spec_key = INIT_TIME_SPEC_KEY,
                    vterm_rms_pu_signal_name=INV1_VTERM_RMS_PU_SIGNAL_NAME,
                    vpoc_pu_command_spec_key=VSLACK_PU_COMMAND_SPEC_KEY_CUO,
                    hvrt_thresholds=HVRT_THRESHOLDS,
                    lvrt_thresholds=LVRT_THRESHOLDS,
                    )
        except Exception as e:
            print("Failed on:    CUO")
            print(e)
            traceback.print_exc()
            errors.append(f"CUO: {e}")
            


    if "Vdroop characteristic" in ANALYSIS_TO_RUN:
        try:
            out_paths = glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR Vgrid Steps") + "/*"+extension)
            
            produce_vdroop_outputs(
                    psout_paths = out_paths,
                    output_png_path=os.path.join(OUTPUTS_DIR, "vdroop_characteristic.png"),
                    output_csv_path=os.path.join(OUTPUTS_DIR, "vdroop_results.csv"),
                    qpoc_mvar_signal_name=QPOC_MVAR_SIGNAL_NAME,
                    vpoc_rms_pu_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                    vref_pu_signal_name=VREF_PU_SIGNAL_NAME,
                    vpoc_pu_command_spec_key=VSLACK_PU_COMMAND_SPEC_KEY_VGRID,
                    vdroop_characteristic_points=VDROOP_CHARACTERISTIC_POINTS,
                    init_time_spec_key = INIT_TIME_SPEC_KEY,
                    df_manipulation_fn = pre_process_dataframe,
                    x86 = x86
                    )
        except Exception as e:
            print("Failed on:   Vdroop Characterisitc")
            print(e)
            errors.append(f"Vdroop characteristic: {e}")
            traceback.print_exc()
            

    if "Vgrid step analysis" in ANALYSIS_TO_RUN:
        out_paths = glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR PFref Steps") + "/*"+extension)
        
        saturated_paths = []
        unsaturated_paths = []
        for path in out_paths:
            json_path = path.replace(extension, ".json")
            with open(json_path,'r') as f: 
                spec = json.load(f)
            if "Saturated_Status" in spec:
                if spec["Saturated_Status"] == "YES":
                    saturated_paths.append(path)
                if spec["Saturated_Status"] == "NO":
                    unsaturated_paths.append(path)

        try:

            if len(saturated_paths)!=0:
                produce_disturbance_analysis_outputs(
                        psout_paths = saturated_paths,
                        output_png_path=os.path.join(OUTPUTS_DIR, "Vgrid PF step disturbance tracking saturated.png"),
                        output_csv_path=os.path.join(OUTPUTS_DIR, "Vgrid PF step disturbance tracking saturated.csv"),
                        disturbance_command_spec_key=VSLACK_PU_COMMAND_SPEC_KEY_PF,
                        ppoc_mw_signal_name=PPOC_MW_SIGNAL_NAME,
                        qpoc_mvar_signal_name=QPOC_MVAR_SIGNAL_NAME,
                        vpoc_pu_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                        perr_mw_signal_name=PERR_MW_SIGNAL_NAME,
                        qerr_mvar_signal_name=QERR_MVAR_SIGNAL_NAME,
                        verr_adj_pu_signal_name=VERR_ADJ_PU_SIGNAL_NAME,
                        rise_settle_title_spec_key="File_Name",
                        pre_step_plot_secs=2.0,
                        pre_error_plot_secs=2.0,
                        init_time_spec_key = INIT_TIME_SPEC_KEY,
                        df_manipulation_fn = pre_process_dataframe,
                        x86 = x86
                        )
        except Exception as e:
            print("Failed on:    Vgrid step analysis (PF)- saturated")
            print(e)
            traceback.print_exc()
            errors.append(f"Vgrid step analysis (PF-sat) : {e}")
            
        try:

            if len(unsaturated_paths)!=0:
                produce_disturbance_analysis_outputs(
                        psout_paths = unsaturated_paths,
                        output_png_path=os.path.join(OUTPUTS_DIR, "Vgrid PF step disturbance tracking unsaturated.png"),
                        output_csv_path=os.path.join(OUTPUTS_DIR, "Vgrid PF step disturbance tracking unsaturated.csv"),
                        disturbance_command_spec_key=VSLACK_PU_COMMAND_SPEC_KEY_PF,
                        ppoc_mw_signal_name=PPOC_MW_SIGNAL_NAME,
                        qpoc_mvar_signal_name=QPOC_MVAR_SIGNAL_NAME,
                        vpoc_pu_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                        perr_mw_signal_name=PERR_MW_SIGNAL_NAME,
                        qerr_mvar_signal_name=QERR_MVAR_SIGNAL_NAME,
                        verr_adj_pu_signal_name=VERR_ADJ_PU_SIGNAL_NAME,
                        rise_settle_title_spec_key="File_Name",
                        pre_step_plot_secs=2.0,
                        pre_error_plot_secs=2.0,
                        init_time_spec_key = INIT_TIME_SPEC_KEY,
                        df_manipulation_fn = pre_process_dataframe,
                        x86 = x86
                        )
        except Exception as e:
            print("Failed on:    Vgrid step analysis (PF) - unsaturated")
            print(e)
            traceback.print_exc()
            errors.append(f"Vgrid step analysis (PF-sat): {e}")
            
        
    if "Vgrid step analysis" in ANALYSIS_TO_RUN:
        
        out_paths = glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR Qref Steps") + "/*"+extension)

        saturated_paths = []
        unsaturated_paths = []
    
        for path in out_paths:
            json_path = path.replace(extension, ".json")
            with open(json_path,'r') as f: 
                spec = json.load(f)
            if "Saturated_Status" in spec:
                if spec["Saturated_Status"] == "YES":
                    saturated_paths.append(path)
                if spec["Saturated_Status"] == "NO":
                    unsaturated_paths.append(path)
    
        try:
            if len(saturated_paths)!=0:
                produce_disturbance_analysis_outputs(
                        psout_paths = saturated_paths,
                        output_png_path=os.path.join(OUTPUTS_DIR, "Vgrid VAr step disturbance tracking saturated.png"),
                        output_csv_path=os.path.join(OUTPUTS_DIR, "Vgrid VAr step disturbance tracking saturated.csv"),
                        disturbance_command_spec_key=QREF_PU_COMMAND_SPEC_KEY,
                        ppoc_mw_signal_name=PPOC_MW_SIGNAL_NAME,
                        qpoc_mvar_signal_name=QPOC_MVAR_SIGNAL_NAME,
                        vpoc_pu_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                        perr_mw_signal_name=PERR_MW_SIGNAL_NAME,
                        qerr_mvar_signal_name=QERR_MVAR_SIGNAL_NAME,
                        verr_adj_pu_signal_name=VERR_ADJ_PU_SIGNAL_NAME,
                        rise_settle_title_spec_key="File_Name",
                        pre_step_plot_secs=2.0,
                        pre_error_plot_secs=2.0,
                        init_time_spec_key = INIT_TIME_SPEC_KEY,
                        df_manipulation_fn = pre_process_dataframe,
                        x86 = x86
                )

        except Exception as e:
            print("Failed on:    Vgrid step analysis (Qcontrol) - saturated")
            print(e)
            traceback.print_exc()
            errors.append(f"Vgrid step analysis (Qcontrol-sat): {e}")
            
        try:
            if len(unsaturated_paths)!=0:
                produce_disturbance_analysis_outputs(
                        psout_paths = unsaturated_paths,
                        output_png_path=os.path.join(OUTPUTS_DIR, "Vgrid VAr step disturbance tracking unsaturated.png"),
                        output_csv_path=os.path.join(OUTPUTS_DIR, "Vgrid VAr step disturbance tracking unsaturated.csv"),
                        disturbance_command_spec_key=QREF_PU_COMMAND_SPEC_KEY,
                        ppoc_mw_signal_name=PPOC_MW_SIGNAL_NAME,
                        qpoc_mvar_signal_name=QPOC_MVAR_SIGNAL_NAME,
                        vpoc_pu_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                        perr_mw_signal_name=PERR_MW_SIGNAL_NAME,
                        qerr_mvar_signal_name=QERR_MVAR_SIGNAL_NAME,
                        verr_adj_pu_signal_name=VERR_ADJ_PU_SIGNAL_NAME,
                        rise_settle_title_spec_key="File_Name",
                        pre_step_plot_secs=2.0,
                        pre_error_plot_secs=2.0,
                        init_time_spec_key = INIT_TIME_SPEC_KEY,
                        df_manipulation_fn = pre_process_dataframe,
                        x86 = x86
                        )
        except Exception as e:
            print("Failed on:    Vgrid step analysis (Qcontrol) - unsaturated")
            print(e)
            traceback.print_exc()
            errors.append(f"Vgrid step analysis (Qcontrol-unsat): {e}")
            

    if "Vgrid step analysis" in ANALYSIS_TO_RUN:
        
        out_paths = glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR Vgrid Steps") + "/*"+extension)
        saturated_paths=[]
        unsaturated_paths = []

        for path in out_paths:
            json_path = path.replace(extension, ".json")
            with open(json_path,'r') as f: 
                spec = json.load(f)
            if "Saturated_Status" in spec:
                if spec["Saturated_Status"] == "YES":
                    saturated_paths.append(path)
                if spec["Saturated_Status"] == "NO":
                    unsaturated_paths.append(path)

 
        try:

            if len(saturated_paths)!=0:
                produce_disturbance_analysis_outputs(
                        psout_paths = saturated_paths,
                        output_png_path=os.path.join(OUTPUTS_DIR, "Vgrid droop step disturbance tracking saturated.png"),
                        output_csv_path=os.path.join(OUTPUTS_DIR, "Vgrid droop step disturbance tracking saturated.csv"),
                        disturbance_command_spec_key=VSLACK_PU_COMMAND_SPEC_KEY_VGRID,
                        ppoc_mw_signal_name=PPOC_MW_SIGNAL_NAME,
                        qpoc_mvar_signal_name=QPOC_MVAR_SIGNAL_NAME,
                        vpoc_pu_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                        perr_mw_signal_name=PERR_MW_SIGNAL_NAME,
                        qerr_mvar_signal_name=QERR_MVAR_SIGNAL_NAME,
                        verr_adj_pu_signal_name=VERR_ADJ_PU_SIGNAL_NAME,
                        rise_settle_title_spec_key="File_Name",
                        pre_step_plot_secs=2.0,
                        pre_error_plot_secs=2.0,
                        init_time_spec_key = INIT_TIME_SPEC_KEY,
                        df_manipulation_fn = pre_process_dataframe,
                        x86 = x86
                        )
                
        except Exception as e:
            print("Failed on:     Vgrid step analysis (Vdroop) - saturated")
            print(e)
            traceback.print_exc()
            errors.append(f"Vgrid step analysis (Vdroop-sat): {e}")
            
        try:
            if len(unsaturated_paths)!=0:
                produce_disturbance_analysis_outputs(
                        psout_paths = unsaturated_paths,
                        output_png_path=os.path.join(OUTPUTS_DIR, "Vgrid droop step disturbance tracking unsaturated.png"),
                        output_csv_path=os.path.join(OUTPUTS_DIR, "Vgrid droop step disturbance tracking unsaturated.csv"),
                        disturbance_command_spec_key=VSLACK_PU_COMMAND_SPEC_KEY_VGRID,
                        ppoc_mw_signal_name=PPOC_MW_SIGNAL_NAME,
                        qpoc_mvar_signal_name=QPOC_MVAR_SIGNAL_NAME,
                        vpoc_pu_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                        perr_mw_signal_name=PERR_MW_SIGNAL_NAME,
                        qerr_mvar_signal_name=QERR_MVAR_SIGNAL_NAME,
                        verr_adj_pu_signal_name=VERR_ADJ_PU_SIGNAL_NAME,
                        rise_settle_title_spec_key="File_Name",
                        pre_step_plot_secs=2.0,
                        pre_error_plot_secs=2.0,
                        init_time_spec_key = INIT_TIME_SPEC_KEY,
                        df_manipulation_fn = pre_process_dataframe,
                        x86 = x86
                        )
        except Exception as e:
            print("Failed on:     Vgrid step analysis (Vdroop) - unsaturated")
            print(e)
            traceback.print_exc()
            errors.append(f"Vgrid step analysis (Vdroop-unsat): {e}")
            
                

#5_2_5_13 -- END       


    if "Vref step analysis" in ANALYSIS_TO_RUN:
    
        out_paths = glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR Vref Steps") + "/*"+extension)
        saturated_paths=[]
        unsaturated_paths = []
    
        for path in out_paths:
            json_path = path.replace(extension, ".json")
            with open(json_path,'r') as f: 
                spec = json.load(f)
            if "Saturated_Status" in spec:
                if spec["Saturated_Status"] == "YES":
                    saturated_paths.append(path)
                if spec["Saturated_Status"] == "NO":
                    unsaturated_paths.append(path)
      

        try:
            if len(saturated_paths)!=0:
                produce_disturbance_analysis_outputs(
                        psout_paths = saturated_paths,
                        output_png_path=os.path.join(OUTPUTS_DIR, "Vref step disturbance tracking saturated.png"),
                        output_csv_path=os.path.join(OUTPUTS_DIR, "Vref step disturbance tracking saturated.csv"),
                        disturbance_command_spec_key=VREF_PU_COMMAND_SPEC_KEY,
                        ppoc_mw_signal_name=PPOC_MW_SIGNAL_NAME,
                        qpoc_mvar_signal_name=QPOC_MVAR_SIGNAL_NAME,
                        vpoc_pu_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                        perr_mw_signal_name=PERR_MW_SIGNAL_NAME,
                        qerr_mvar_signal_name=QERR_MVAR_SIGNAL_NAME,
                        verr_adj_pu_signal_name=VERR_ADJ_PU_SIGNAL_NAME,
                        rise_settle_title_spec_key="File_Name",
                        init_time_spec_key = INIT_TIME_SPEC_KEY,
                        df_manipulation_fn = pre_process_dataframe,
                        x86 = x86
                        )
        except Exception as e:
            print("Failed on:    Vref step analysis - saturated")
            print(e)
            traceback.print_exc()
            errors.append(f"Vref step analysis (sat): {e}")
            
        try:
            if len(unsaturated_paths)!=0:
                produce_disturbance_analysis_outputs(
                        psout_paths = unsaturated_paths,
                        output_png_path=os.path.join(OUTPUTS_DIR, "Vref step disturbance tracking saturated.png"),
                        output_csv_path=os.path.join(OUTPUTS_DIR, "Vref step disturbance tracking saturated.csv"),
                        disturbance_command_spec_key=VREF_PU_COMMAND_SPEC_KEY,
                        ppoc_mw_signal_name=PPOC_MW_SIGNAL_NAME,
                        qpoc_mvar_signal_name=QPOC_MVAR_SIGNAL_NAME,
                        vpoc_pu_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                        perr_mw_signal_name=PERR_MW_SIGNAL_NAME,
                        qerr_mvar_signal_name=QERR_MVAR_SIGNAL_NAME,
                        verr_adj_pu_signal_name=VERR_ADJ_PU_SIGNAL_NAME,
                        rise_settle_title_spec_key="File_Name",
                        init_time_spec_key = INIT_TIME_SPEC_KEY,
                        df_manipulation_fn = pre_process_dataframe,
                        x86 = x86
                        )
        except Exception as e:
            print("Failed on:     Vref step analysis - unsaturated")
            print(e)
            traceback.print_exc()
            errors.append(f"Vref step analysis (unsat): {e}")
            
                
            
    

    if "Qref step analysis" in ANALYSIS_TO_RUN:
        
        out_paths = glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR Qref Steps") + "/*"+extension)
        # print(out_paths)
        saturated_paths=[]
        unsaturated_paths = []
        for path in out_paths:
            json_path = path.replace(extension, ".json")
            with open(json_path,'r') as f: 
                spec = json.load(f)
            # if "Saturated_Status" in spec:
            #     if spec["Saturated_Status"] == "YES":
            #         saturated_paths.append(path)
            #     if spec["Saturated_Status"] == "NO":
            #         unsaturated_paths.append(path)

        try:

            # if len(saturated_paths)!=0:
                produce_disturbance_analysis_outputs(
                        psout_paths = out_paths,
                        output_png_path=os.path.join(OUTPUTS_DIR, "Qref step disturbance tracking.png"),
                        output_csv_path=os.path.join(OUTPUTS_DIR, "Qref step disturbance tracking.csv"),
                        disturbance_command_spec_key=QREF_PU_COMMAND_SPEC_KEY,
                        ppoc_mw_signal_name=PPOC_MW_SIGNAL_NAME,
                        qpoc_mvar_signal_name=QPOC_MVAR_SIGNAL_NAME,
                        vpoc_pu_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                        perr_mw_signal_name=PERR_MW_SIGNAL_NAME,
                        qerr_mvar_signal_name=QERR_MVAR_SIGNAL_NAME,
                        verr_adj_pu_signal_name=VERR_ADJ_PU_SIGNAL_NAME,
                        rise_settle_title_spec_key="File_Name",
                        init_time_spec_key = INIT_TIME_SPEC_KEY,
                        df_manipulation_fn = pre_process_dataframe,
                        x86 = x86
                        )
        except Exception as e:
            print("Failed on:    Qref step analysis - saturated")
            print(e)
            traceback.print_exc()
            errors.append(f"Qref step analysis (sat): {e}")
            

        # try:
        #     if len(unsaturated_paths)!=0:
        #         produce_disturbance_analysis_outputs(
        #                 psout_paths = unsaturated_paths,
        #                 output_png_path=os.path.join(OUTPUTS_DIR, "Qref step disturbance tracking unsaturated.png"),
        #                 output_csv_path=os.path.join(OUTPUTS_DIR, "Qref step disturbance tracking unsaturated.csv"),
        #                 disturbance_command_spec_key=QREF_PU_COMMAND_SPEC_KEY,
        #                 ppoc_mw_signal_name=PPOC_MW_SIGNAL_NAME,
        #                 qpoc_mvar_signal_name=QPOC_MVAR_SIGNAL_NAME,
        #                 vpoc_pu_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
        #                 perr_mw_signal_name=PERR_MW_SIGNAL_NAME,
        #                 qerr_mvar_signal_name=QERR_MVAR_SIGNAL_NAME,
        #                 verr_adj_pu_signal_name=VERR_ADJ_PU_SIGNAL_NAME,
        #                 rise_settle_title_spec_key="File_Name",
        #                 init_time_spec_key = INIT_TIME_SPEC_KEY,
        #                 df_manipulation_fn = pre_process_dataframe,
        #                 x86 = x86
        #                 )
        # except Exception as e:
        #     print("Failed on:    Qref step analysis - saturated")
        #     print(e)
        #     traceback.print_exc()
        #     errors.append(f"Qref step analysis (unsat): {e}")
            


    if "PFref step analysis" in ANALYSIS_TO_RUN:
        out_paths = glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR PFref Steps") + "/*"+extension)
        saturated_paths=[]
        unsaturated_paths = []
        for path in out_paths:
            json_path = path.replace(extension, ".json")
            with open(json_path,'r') as f: 
                spec = json.load(f)
            if "Saturated_Status" in spec:
                if spec["Saturated_Status"] == "YES":
                    saturated_paths.append(path)
                if spec["Saturated_Status"] == "NO":
                    unsaturated_paths.append(path)

        try:
            if len(saturated_paths)!=0:
                produce_disturbance_analysis_outputs(
                        psout_paths = saturated_paths,
                        output_png_path=os.path.join(OUTPUTS_DIR, "PFref step disturbance tracking saturated.png"),
                        output_csv_path=os.path.join(OUTPUTS_DIR, "PFref step disturbance tracking saturated.csv"),
                        disturbance_command_spec_key=PFREF_PU_COMMAND_SPEC_KEY,
                        ppoc_mw_signal_name=PPOC_MW_SIGNAL_NAME,
                        qpoc_mvar_signal_name=QPOC_MVAR_SIGNAL_NAME,
                        vpoc_pu_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                        perr_mw_signal_name=PERR_MW_SIGNAL_NAME,
                        qerr_mvar_signal_name=QERR_MVAR_SIGNAL_NAME,
                        verr_adj_pu_signal_name=VERR_ADJ_PU_SIGNAL_NAME,
                        rise_settle_title_spec_key="File_Name",
                        init_time_spec_key = INIT_TIME_SPEC_KEY,
                        df_manipulation_fn = pre_process_dataframe,
                        x86 = x86
                        )
        except Exception as e:
            print("Failed on:    PFref step analysis - saturated")
            print(e)
            traceback.print_exc()
            errors.append(f"PFref step analysis (sat): {e}")
            
        try:
            if len(unsaturated_paths)!=0:
                produce_disturbance_analysis_outputs(
                        psout_paths = unsaturated_paths,
                        output_png_path=os.path.join(OUTPUTS_DIR, "PFref step disturbance tracking unsaturated.png"),
                        output_csv_path=os.path.join(OUTPUTS_DIR, "PFref step disturbance tracking unsaturated.csv"),
                        disturbance_command_spec_key=PFREF_PU_COMMAND_SPEC_KEY,
                        ppoc_mw_signal_name=PPOC_MW_SIGNAL_NAME,
                        qpoc_mvar_signal_name=QPOC_MVAR_SIGNAL_NAME,
                        vpoc_pu_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                        perr_mw_signal_name=PERR_MW_SIGNAL_NAME,
                        qerr_mvar_signal_name=QERR_MVAR_SIGNAL_NAME,
                        verr_adj_pu_signal_name=VERR_ADJ_PU_SIGNAL_NAME,
                        rise_settle_title_spec_key="File_Name",
                        init_time_spec_key = INIT_TIME_SPEC_KEY,
                        df_manipulation_fn = pre_process_dataframe,
                        x86 = x86
                        )
        except Exception as e:
            print("Failed on:    PFref step analysis - unsaturated")
            print(e)
            traceback.print_exc()
            errors.append(f"PFref step analysis (unsat): {e}")
            

    if "diq/dV characteristic" in ANALYSIS_TO_RUN:

        try:
            produce_s5255_iq_outputs(
                    fault_psout_paths=glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR Balanced Faults") + "/*"+extension)[:],
                    tov_psout_paths=glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR TOV") + "/*"+extension)[:],
                    output_png_path=os.path.join(OUTPUTS_DIR, "diqdv_characteristic.png"),
                    output_csv_path=os.path.join(OUTPUTS_DIR, "diqdv_results.csv"),
                    groupby_str_for_plot_titles=None,
                    diqdv_characteristic_points=DIQDV_CHARACTERISTIC_POINTS,
                    init_time_spec_key=INIT_TIME_SPEC_KEY,
                    fault_timing_signal_command_spec_key=FAULT_TIMING_SIGNAL_COMMAND_SPEC_KEY,
                    tov_timing_signal_command_spec_key=TOV_TIMING_SIGNAL_COMMAND_SPEC_KEY,
                    iq_pos_seq_signal_name=POC_IQ_POS_SIGNAL_NAME,
                    iq_neg_seq_signal_name="NA",
                    v_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                    saturation_current_signal_name=POC_IRMS_PU_SIGNAL_NAME,
                    included_voltage_ranges=DIQDV_INCLUDED_VOLTAGE_RANGES,
                    y_label=u'Change in Reactive Current, Δ$I_{q}$ (pu)',
                    x_label=u'Point of Connection Voltage, $V_{fault,settled}$ (pu)',
                    df_manipulation_fn = pre_process_dataframe,
                    x86 = x86
                    )
        except Exception as e:
            print("Failed on:   diq/dV characteristic")
            print(e)
            traceback.print_exc()
            errors.append(f"diq/dV characteristic (diqdv): {e}")
            
        try:
            produce_s5255_iq_outputs(
                    fault_psout_paths=glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR Balanced Faults") + "/*"+extension)[:],
                    tov_psout_paths=glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR TOV") + "/*"+extension)[:],
                    output_png_path=os.path.join(OUTPUTS_DIR, "inv1_diqdv_characteristic.png"),
                    output_csv_path=os.path.join(OUTPUTS_DIR, "inv1_diqdv_results.csv"),
                    groupby_str_for_plot_titles=None,
                    diqdv_characteristic_points=DIQDV_INV_CHARACTERISTIC_POINTS,
                    init_time_spec_key=INIT_TIME_SPEC_KEY,
                    fault_timing_signal_command_spec_key=FAULT_TIMING_SIGNAL_COMMAND_SPEC_KEY,
                    tov_timing_signal_command_spec_key=TOV_TIMING_SIGNAL_COMMAND_SPEC_KEY,
                    iq_pos_seq_signal_name=INV1_IQ_POS_SIGNAL_NAME,
                    iq_neg_seq_signal_name="NA",
                    v_signal_name=INV1_VTERM_RMS_PU_SIGNAL_NAME,
                    saturation_current_signal_name=POC_IRMS_PU_SIGNAL_NAME,
                    included_voltage_ranges=DIQDV_INV_INCLUDED_VOLTAGE_RANGES,
                    y_label=u'Change in Reactive Current, Δ$I_{q}$ (pu)',
                    x_label=u'Terminal Voltage, $V_{fault,settled}$ (pu)',
                    df_manipulation_fn = pre_process_dataframe,
                    x86 = x86
                    )
        except Exception as e:
            print("Failed on:   diq/dV characteristic")
            print(e)
            traceback.print_exc()
            errors.append(f"diq/dV characteristic (inv1-diqdv): {e}")
            
            

    if "Frequency ride-through characteristic" in ANALYSIS_TO_RUN:
        try:
            out_paths = glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR F Withstand") + "/*"+extension)[:]
        
            produce_cumulative_ride_through_outputs(
                    psout_paths = out_paths,
                    output_png_path=os.path.join(OUTPUTS_DIR, "s5253_ride_through_results.png"),
                    output_csv_path=os.path.join(OUTPUTS_DIR, "s5253_ride_through_results.csv"),
                    step_size=0.05,
                    init_time_spec_key=INIT_TIME_SPEC_KEY,
                    measurement_signal_name=FPOC_HZ_SIGNAL_NAME,
                    high_characteristic_points=HFRT_CHARACTERISTIC_POINTS,
                    low_characteristic_points=LFRT_CHARACTERISTIC_POINTS,
                    #error_signal_name=ERROR_SIGNAL_NAME,
                    df_manipulation_fn=pre_process_dataframe,
                    title="Frequency ride-through",
                    y_label="Frequency (Hz)",
                    x86 = x86,
                    )
        except Exception as e:
            print("Failed on:    Frequency ride-through characteristic")
            print(e)
            traceback.print_exc()
            errors.append(f"Frequency ride-through characteristic: {e}")
            

        

    if "Voltage ride-through characteristic" in ANALYSIS_TO_RUN:

        out_paths = glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR V Withstand") + "/*"+extension)[:]
        filtered_paths = []
        for path in out_paths:
            json_path = path.replace(extension, ".json")
            with open(json_path,'r') as f:
                spec = json.load(f)
            if "Envelope" in spec:
                if spec["Envelope"] == "YES":
                    filtered_paths.append(path)
  

        try:
            produce_cumulative_ride_through_outputs(
                    psout_paths = filtered_paths,
                    output_png_path=os.path.join(OUTPUTS_DIR, "s5254_ride_through_results_zoom.png"),
                    output_csv_path=os.path.join(OUTPUTS_DIR, "s5254_ride_through_results_zoom.csv"),
                    step_size=0.001,
                    init_time_spec_key=INIT_TIME_SPEC_KEY,
                    measurement_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                    high_characteristic_points=HVRT_CHARACTERISTIC_POINTS,
                    low_characteristic_points=LVRT_CHARACTERISTIC_POINTS,
                    #error_signal_name=ERROR_SIGNAL_NAME,
                    df_manipulation_fn=pre_process_dataframe,
                    title="Voltage ride-through",
                    y_label="Voltage (pu)",
                    x_axis_min=0.0,
                    x_axis_max=1215.0,
                    x86 = x86,
                        )
        except Exception as e:
            print("Failed on:    Voltage ride-through characteristic")
            print(e)
            traceback.print_exc()
            errors.append(f"Voltage ride-through characteristic: {e}")


    if "IQ Rise Settle & P Recovery Curve" in ANALYSIS_TO_RUN:
        try:
            produce_s5255_rise_settle_recovery_curve(
                    psout_paths=glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR Balanced Faults") + "/*"+extension),
                    output_dir=os.path.join(OUTPUTS_DIR,"S5255 Balanced Faults Rise Settle Recovery Analysis"),
                    disturbance_command_spec_key=FAULT_TIMING_SIGNAL_COMMAND_SPEC_KEY,
                    ppoc_mw_signal_name=PPOC_MW_SIGNAL_NAME,
                    iq_pu_signal_name=POC_IQ_POS_SIGNAL_NAME, 
                    vpoc_pu_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                    rise_settle_title_spec_key="File_Name",
                    pre_step_plot_secs=2.0,
                    df_manipulation_fn = pre_process_dataframe,
                    x86 = x86
                )
        except Exception as e:
            print("Failed on:    IQ Rise Settle & P Recovery Curve - Balanced faults")
            print(e)
            traceback.print_exc()
            errors.append(f"IQ Rise Settle & P Recovery Curve (bal): {e}")
            

        try:
            produce_s5255_rise_settle_recovery_curve(
                    psout_paths=glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR TOV") + "/*"+extension),
                    output_dir=os.path.join(OUTPUTS_DIR,"S5255 TOV Rise Settle Recovery Analysis"),
                    disturbance_command_spec_key=TOV_TIMING_SIGNAL_COMMAND_SPEC_KEY,
                    ppoc_mw_signal_name=PPOC_MW_SIGNAL_NAME,
                    iq_pu_signal_name=POC_IQ_POS_SIGNAL_NAME, 
                    vpoc_pu_signal_name=VPOC_RMS_PU_SIGNAL_NAME,
                    rise_settle_title_spec_key="File_Name",
                    pre_step_plot_secs=2.0,
                    df_manipulation_fn = pre_process_dataframe,
                    x86 = x86
                )
        except Exception as e:
            print("Failed on:    IQ Rise Settle & P Recovery Curve- TOV")
            print(e)
            traceback.print_exc()
            errors.append(f"IQ Rise Settle & P Recovery Curve (TOV): {e}")
            


    if "S5258 Active Power Reduction" in ANALYSIS_TO_RUN:

        out_paths = glob.glob(os.path.join(CSR_INPUTS_DIR, "CSR Fgrid Steps") + "/*"+extension)
        filtered_paths = [s for s in out_paths if "52511" in s]
        try:
            p_reduction_table(
                psout_paths=filtered_paths,
                freq_channel_key=FPOC_HZ_SIGNAL_NAME,
                active_power_channel_key=PPOC_MW_SIGNAL_NAME,
                output_csv_path=os.path.join(OUTPUTS_DIR, "Active Power Reduction Analysis.csv"),
                p_ramp_down_threshold = 0.5,
                freq_init_ramp_down = 51.0,
                freq_complete_ramp_down = 52.0,
                df_manipulation_fn = pre_process_dataframe,
                x86 = x86
                )
        except Exception as e:
            print("Failed on:    S5258 Active Power Reduction")
            print(e)
            traceback.print_exc()
            errors.append(f"S5258 Active Power Reduction: {e}")
   

    print("\n")
    print("FINISHED ANALYSIS.\n")
    print("All the Errors Encountered:")
    if len(errors)==0:
        print("No errors")
    else:
        for idx,error in enumerate(errors):
            print(f"{idx+1}. {error}\n")
   
    return errors






