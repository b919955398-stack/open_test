import os
import sys
from pathlib import Path

import pandas as pd


# Prefer this project's open/native packages over an older installation.
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from hbess_open.open_psse.specs import load_specs_from_multiple_xlsx, now_str
from hbess_open.plotting.hbess_psse_plotter import HbessPssePlotter
from hbess_open.plotting.process_and_calc_psse import pre_process_dataframe
from hbess_open.studyrunners.psse_study_runner import get_vslacks, run_psse_studies
from hbess_open.analysis.run_analysis_psse import run_analysis_psse
from hbess_open.plotting.replotters import replot_psse
from hbess_open.appendices.create_appendix import create_appendix_heywoodbess
from hbess_open.report_tables.create_report_tables_spec import create_report_table_CSR_DMAT


#------------------------------------------------------------------ CLAUSES --------------------------------------------------------------------------------------
x86 = True
NOW_STR = now_str()
APPENDIX_PROJECT_NAME = "Heywood BESS"

SHEETS_TO_PROCESS_CSR = [
    # "5253_F", #working
    # "5254_Withstand", #bad results
    # "5254_CUO", #working
    # "5255_TOV", #working
    # "5255_UnbalFaults",
    # "5255_BalFaults",
    # "5257_PLR",
    # "52511_Fgrid",
    # "52511_Fgrid_AEMO_discussion",
    # "52513_Vgrid_droop",
    # "52513_Vref",
    # "52513_Qref",
    # "52513_PFref",
    # "52514_Pref",
    # "5258_Fprotection",
    # "5258_Vprotection",
    # "S5258_PhaseSteps",
    # "52515_SCR_Withstand_Faults",
    # "52515_Vgrid",
    # "52515_SCR_Change_NoFault",
    # "5258_ActivePowerReduction",
    # "MFRT",
    # "5255_BalFaults_DD_R2"
]


SHEETS_TO_PROCESS_DMAT = [
    # "324_325_Faults",
    # "326_MFRT",
    "329_TOV",
    "3210_Vref",
    "3210_Qref",
    "3210_PFref",
    "3211_Pref",
    "3217_Pref_POC_SCR1",
    "3212_Fgrid",
    "3210_3214_Vgrid",
    "3216_PhaseSteps",
    "3218_SCR_Change_Faults_SCR1",
    "3219_POC_SCR_Faults",
]

SHEETS_TO_PROCESS_DMAT_CRG = [
    # "324_325_Faults_CRG",
    # "326_MFRT_CRG",
    # "329_TOV_CRG",
    # "3210_Vref_CRG",
    # "3210_Qref_CRG",
    # "3210_PFref_CRG",
    # "3211_Pref_CRG",
    # "3217_Pref_POC_SCR1_CRG",
    # "3212_Fgrid_CRG",
    # "3210_3214_Vgrid_CRG",
    # "3216_PhaseSteps_CRG",
    # "3218_SCR_Change_Faults_SCR1_CRG",
    # "3219_POC_SCR_Faults_CRG",
]

SHEETS_TO_PROCESS_FLATRUN = [
    # "CORNER_POINTS",
]


ANALYSIS_TO_RUN = [

            # "dP/df characteristic",


            # "CUO",

# # 5.2.5.13
            # "Vdroop characteristic",
            # "Vgrid step analysis",
            # "Vref step analysis",
            # "Qref step analysis",
            # "PFref step analysis",

# # # # 5.2.5.8
            # "S5258 Active Power Reduction"
# # # 5.5
            # "diq/dV characteristic",
            # "IQ Rise Settle & P Recovery Curve",
# # # 5.3
            # "Frequency ride-through characteristic",
# # # 5.4
            # "Voltage ride-through characteristic",


            ]

#------------------------------------------------------------------ END OF CLAUSES --------------------------------------------------------------------------------------



#----------------------------------------------------------------------------- SET RUN SETTINGS + PATHS  ------------------------------------------------------------------------------
SAV_VERSION = "v0-0-4"
DYR_VERSION = "v0-0-4"

XLSX_DIR = r"C:\Users\AlvinBai\Grid-Link\Projects - Documents\Atmos\Heywood BESS R0\02_Deliverables\PROJECT_SPEC"
XLSX_PATH_CSR = os.path.join(XLSX_DIR, "HY_Spec_CSR_300.xlsx")
XLSX_PATH_DMAT = os.path.join(XLSX_DIR, "HY_Spec_DMAT.xlsx")
XLSX_PATH_DMAT_CRG = os.path.join(XLSX_DIR, "HY_Spec_DMAT_CRG.xlsx")
XLSX_PATH_DMAT_FLATRUN = os.path.join(XLSX_DIR, "HY_Spec_FLATTEST.xlsx")
#FLATRUN_XLSX = os.path.join(r"C:\Grid\chen\cg\psse\flatrun_spec", "CGBess_Spec_Flatrun.xlsx")


RUN_STUDIES = True
if RUN_STUDIES:
    slack_bus_num = 331182
    MODEL_DIR = r"""C:\Grid\WorkFolder\Heywood work folder\open test\psse model"""
    plotter = HbessPssePlotter(pre_process_fn=pre_process_dataframe)
    RESULTS_DIR = os.path.join(
        r"""C:\Grid\WorkFolder\Heywood work folder\open test""",
        f"{SAV_VERSION}_sav_{DYR_VERSION}_dyr",
        now_str(),
    )
    if not os.path.exists(RESULTS_DIR):
        os.makedirs(RESULTS_DIR)

    #Filtering spec
    specification = load_specs_from_multiple_xlsx(
        [XLSX_PATH_CSR, XLSX_PATH_DMAT, XLSX_PATH_DMAT_CRG, XLSX_PATH_DMAT_FLATRUN],
        sheet_names=[
            SHEETS_TO_PROCESS_CSR,
            SHEETS_TO_PROCESS_DMAT,
            SHEETS_TO_PROCESS_DMAT_CRG,
            SHEETS_TO_PROCESS_FLATRUN,
        ],
    )
    spec = get_vslacks(specification, MODEL_DIR, slack_bus_num)
    if "Vslack_pu_psse" in spec.columns:
        spec_non_vslack = specification[
            ~specification["Vslack_pu_psse"].astype(str).str.contains(r"\$VSLACK")
        ]
    else:
        spec_non_vslack = specification
    spec = pd.concat([spec, spec_non_vslack], ignore_index=True)
    spec = spec[spec["PSSE"] == True]
    # print(spec["Vslack_pu_psse"])
    # spec_vslack_df = pd.DataFrame(spec, columns=["Vslack_pu_psse"])
    # spec_vslack_df.to_csv("spec.csv")
    # sys.exit()

    # spec = spec[spec["Test No"].isin([10,11,12,13,14,15,16,17,18])]
    # spec = spec[spec["Test No"] <= 12]
    # spec = spec[spec["Subtest No"] == 5]
    # spec = spec[spec["Batch"] == 2]


RUN_ANALYSIS = False
if RUN_ANALYSIS:
    if RUN_STUDIES:
        CSR_INPUTS_DIR = RESULTS_DIR
    else:
        CSR_INPUTS_DIR = r"""D:\results\heywoodbess\psse\EXISTING_RUN"""
    analysis_extension = ".out"
    ANALYSIS_OUTPUTS_DIR = os.path.join(CSR_INPUTS_DIR, f"_analysis_{NOW_STR}")

    DPDF_CHARACTERISTIC_POINTS = [(-6, 570), (-1.715, 570), (-0.865, 285), (-0.1, 11.4), (-0.015, 0), (0.015, 0), (0.1, -11.4), (0.865, -285), (1.715, -570), (6, -570)]
    VDROOP_CHARACTERISTIC_POINTS = [(-0.1, 112.575), (-0.04, 112.575), (-0.04, 112.575), (0.04, -112.575), (0.04, -112.575), (0.1, -112.575)]

    HVRT_THRESHOLDS = [
            {
                "value": 1.15,
                "withstand_sec": 60,
                "colour": "yellow",
            },
            {
                "value": 1.25,
                "withstand_sec": 1,
                "colour": "orange",
            },
        ]
    LVRT_THRESHOLDS = [
            {
                "value": 0.8,
                "withstand_sec": 21,
                "colour": "yellow",
            },
            {
                "value": 0.4,
                "withstand_sec": 21,
                "colour": "red",
            },
        ]


#Replot PSSE studies
REPLOT_PSSE = False
if REPLOT_PSSE:
    extension_replot = ".out"
    replotter = HbessPssePlotter(pre_process_fn=pre_process_dataframe)
    PLOT_INPUTS_DIR = r"""C:\Grid\chen\cg\results\psse\v1-1-0_sav_v1-1-0_dyr\20250326_1234_16856156"""
    PLOT_OUT_PATH = os.path.join(r"""C:\Grid\chen\cg\results\psse\replots""")


#Generate appendices for chosen clauses
CREATE_APPENDIX = False
if CREATE_APPENDIX:
    PLOT_RESULTS_DIRS = [RESULTS_DIR]
    OUTPUT_DIR_DMAT = os.path.join(RESULTS_DIR)
    OUTPUT_DIR_CSR = os.path.join(RESULTS_DIR)
    SHEETS_TO_PROCESS_COMBINED = [SHEETS_TO_PROCESS_CSR, SHEETS_TO_PROCESS_DMAT, SHEETS_TO_PROCESS_DMAT_CRG]
    XLSX_PATHS = [XLSX_PATH_CSR, XLSX_PATH_DMAT, XLSX_PATH_DMAT_CRG]
    issued_date = "20th July 2026"
    revision_no = "DRAFT"
    overwrite_title = False
    hard_title = "Appendix"
    report_no = "004"
    PSSE_REPORT = True
    create_discharge_appendices = True
    create_charge_appendices = True

    if not os.path.exists(OUTPUT_DIR_DMAT):
        os.makedirs(OUTPUT_DIR_DMAT)
    if not os.path.exists(OUTPUT_DIR_CSR):
        os.makedirs(OUTPUT_DIR_CSR)
    print(OUTPUT_DIR_DMAT)


#Create report tables for chosen clauses
CREATE_REPORT_TABLES = False
if CREATE_REPORT_TABLES:
    SHEETS_TO_PROCESS_TABLES = [SHEETS_TO_PROCESS_CSR, SHEETS_TO_PROCESS_DMAT, SHEETS_TO_PROCESS_DMAT_CRG]
    SPEC_PATHS_TABLES = [XLSX_PATH_CSR, XLSX_PATH_DMAT, XLSX_PATH_DMAT_CRG]
    TABLE_DIR = str(PROJECT_ROOT / "002 report tables")
    COLMAP_PATHS = [os.path.join(TABLE_DIR, "column_mapping_DMAT.csv"), os.path.join(TABLE_DIR, "column_mapping_CSR.csv")]
    OUTPUT_DIRS_TABLE = [
        r"""D:\results\heywoodbess\report_tables\tableoutputsDMAT - psse""",
        r"""D:\results\heywoodbess\report_tables\tableoutputsCSR - psse""",
    ]
    for output_dirs in OUTPUT_DIRS_TABLE:
        if not os.path.exists(output_dirs):
            os.makedirs(output_dirs)




#-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":

    if RUN_STUDIES:
        run_psse_studies(
            spec=spec,
            plotter=plotter,
            MODEL_DIR=MODEL_DIR,
            RESULTS_DIR=RESULTS_DIR
        )


    if RUN_ANALYSIS:
        run_analysis_psse(
            x86=x86,
            extension=analysis_extension,
            ANALYSIS_TO_RUN=ANALYSIS_TO_RUN,
            DPDF_CHARACTERISTIC_POINTS=DPDF_CHARACTERISTIC_POINTS,
            VDROOP_CHARACTERISTIC_POINTS=VDROOP_CHARACTERISTIC_POINTS,
            HVRT_THRESHOLDS=HVRT_THRESHOLDS,
            LVRT_THRESHOLDS=LVRT_THRESHOLDS,
            CSR_INPUTS_DIR=CSR_INPUTS_DIR,
            OUTPUTS_DIR=ANALYSIS_OUTPUTS_DIR,
        )


    if REPLOT_PSSE:
        replot_psse(
            extension=extension_replot,
            replotter=replotter,
            PLOT_INPUTS_DIR=PLOT_INPUTS_DIR,
            PLOT_OUT_DIR=PLOT_OUT_PATH,
            x86=x86)


    if CREATE_APPENDIX:
        create_appendix_heywoodbess(
                PLOT_RESULTS_DIRS=PLOT_RESULTS_DIRS,
                OUTPUT_DIR_DMAT=OUTPUT_DIR_DMAT,
                OUTPUT_DIR_CSR=OUTPUT_DIR_CSR,
                XLSX_PATHS=XLSX_PATHS,
                SHEETS_TO_PROCESS=SHEETS_TO_PROCESS_COMBINED,
                NOW_STR=NOW_STR,
                issued_date=issued_date,
                revision_no=revision_no,
                x86=PSSE_REPORT,
                overwrite_title=overwrite_title,
                hard_title=hard_title,
                report_no=report_no,
                create_discharge_appendices=create_discharge_appendices,
                create_charge_appendices=create_charge_appendices)



    if CREATE_REPORT_TABLES:
        create_report_table_CSR_DMAT(
            COLMAP_PATHS=COLMAP_PATHS,
            SPEC_PATHS=SPEC_PATHS_TABLES,
            SHEETS_TO_PROCESS=SHEETS_TO_PROCESS_TABLES,
            OUTPUT_DIRS=OUTPUT_DIRS_TABLE,
            x86=x86)
