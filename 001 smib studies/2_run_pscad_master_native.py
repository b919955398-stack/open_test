"""Heywood BESS PSCAD workflow master.

This outer file intentionally contains configuration and orchestration only.
Open Vslack/TOV initialisation, analysis of existing results, replotting,
appendices and report tables call implementations under ``src``. PSCAD launch
and simulation execution remain reserved for the next implementation stage.
"""

import os
import sys
from pathlib import Path


# -----------------------------------------------------------------------------
# LOCAL PACKAGE PRIORITY
# -----------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import hbess_open
from hbess_open.analysis.run_analysis_pscad import list_pscad_clause_handlers, run_analysis_pscad
from hbess_open.appendices.create_appendix import create_appendix_heywoodbess
from hbess_open.initialisation import prepare_pscad_spec
from hbess_open.open_psse.specs import load_spec_options, now_str, spec_source_lists
from hbess_open.plotting.replotters import replot_pscad
from hbess_open.report_tables.create_report_tables_spec import create_report_table_CSR_DMAT
from hbess_open.studyrunners.pscad_study_runner import run_pscad_studies


# -----------------------------------------------------------------------------
# CLAUSES
# -----------------------------------------------------------------------------

x86 = False
NOW_STR = now_str()
APPENDIX_PROJECT_NAME = "Heywood BESS"

# Project-specific sheet selections are intentionally blank in this framework.
SHEETS_TO_PROCESS_CSR = [
    # "5254_CUO",
    # "5255_UnbalFaults",
    # "5255_BalFaults",
    # "52511_Fgrid",
    # "52513_Vgrid_droop",
    # "52513_Vref",
    # "52513_Qref",
    # "5258_Fprotection",
    # "5258_Vprotection",
    # "5258_ActivePowerReduction",
    # "MFRT",
]

SHEETS_TO_PROCESS_DMAT = [
    # "324_325_Faults",
    # "326_MFRT",
    # "3210_Vref",
    # "3210_Qref",
    # "3212_Fgrid",
    # "3210_3214_Vgrid",
    # "3215_ORT",
]

SHEETS_TO_PROCESS_DMAT_CRG = [
    # "324_325_Faults_CRG",
    # "326_MFRT_CRG",
    # "3210_Vref_CRG",
    # "3210_Qref_CRG",
    # "3212_Fgrid_CRG",
    # "3210_3214_Vgrid_CRG",
    # "3215_ORT_CRG",
]

SHEETS_TO_PROCESS_FLAT = [
    # "CORNER_POINTS",
    # "DMAT_POINTS",
    # "LOW_SCR_POINTS",
]

ANALYSIS_TO_RUN = [
    # "dP/df characteristic",
    # "CUO",
    # "Vdroop characteristic",
    # "Vgrid step analysis",
    # "Vref step analysis",
    # "Qref step analysis",
    # "PFref step analysis",
    # "diq/dV characteristic",
    # "Frequency ride-through characteristic",
    # "Voltage ride-through characteristic",
    # "IQ Rise Settle & P Recovery Curve",
    # "S5258 Voltage protection analysis",
    # "S5258 Active Power Reduction",
    # "ORT Analysis",
    # "Max fault current",
    # "MFRT",
    # "Phase Health Analysis",
]


# -----------------------------------------------------------------------------
# RUN SETTINGS + PATHS
# -----------------------------------------------------------------------------

# Replace these placeholders only after the project/model settings are agreed.
XLSX_DIR = r"C:\path\to\PROJECT_SPEC"
XLSX_PATH_CSR = os.path.join(XLSX_DIR, "HY_Spec_CSR_300.xlsx")
XLSX_PATH_DMAT = os.path.join(XLSX_DIR, "HY_Spec_DMAT.xlsx")
XLSX_PATH_DMAT_CRG = os.path.join(XLSX_DIR, "HY_Spec_DMAT_CRG.xlsx")
XLSX_PATH_FLAT = os.path.join(XLSX_DIR, "HY_Spec_FLATTEST.xlsx")

MODEL_DIR = r"C:\path\to\PSCAD_MODEL"
RESULTS_ROOT = r"D:\path\to\PSCAD_RESULTS"
STUDY_RESULTS_DIR = os.path.join(RESULTS_ROOT, "_pscad_results_{}".format(NOW_STR))


# -----------------------------------------------------------------------------
# SPEC OPTIONS -- ONE SOURCE OF TRUTH FOR EVERY WORKFLOW
# -----------------------------------------------------------------------------

SPEC_OPTIONS = {
    "sources": [
        {
            "name": "CSR",
            "path": XLSX_PATH_CSR,
            "sheets": SHEETS_TO_PROCESS_CSR,
            "enabled": True,
            "workflows": ["studies", "appendix", "tables"],
        },
        {
            "name": "DMAT",
            "path": XLSX_PATH_DMAT,
            "sheets": SHEETS_TO_PROCESS_DMAT,
            "enabled": True,
            "workflows": ["studies", "appendix", "tables"],
        },
        {
            "name": "DMAT_CRG",
            "path": XLSX_PATH_DMAT_CRG,
            "sheets": SHEETS_TO_PROCESS_DMAT_CRG,
            "enabled": True,
            "workflows": ["studies", "appendix", "tables"],
        },
        {
            "name": "FLAT",
            "path": XLSX_PATH_FLAT,
            "sheets": SHEETS_TO_PROCESS_FLAT,
            "enabled": True,
            "workflows": ["studies"],
        },
    ],
    "enabled_only": True,
    "enabled_column": "PSCAD",
    "filters": {
        # "Test No": {"==": 1},
        # "Subtest No": {"in": [1, 2]},
    },
    "include_categories": [],
    "exclude_categories": [],
    "include_file_names": [],
    "exclude_file_names": [],
    "text_filter": None,
    "limit": None,
    "strict_sheets": True,
    "duplicate_policy": "error",
}


# -----------------------------------------------------------------------------
# PREPARE / RUN PSCAD STUDIES
# -----------------------------------------------------------------------------

# This stage is usable now: it loads the selected SPEC, calculates Vslack,
# optionally calculates TOV shunts, expands $VSLACK and writes one compact CSV.
# PSCAD launch/project/volley execution remains the reserved boundary below.
PREPARE_PSCAD_SPEC = False
RUN_STUDIES = False

USE_VSLACK_CACHE = False
CALC_TOV_SHUNT_VAR = False  # False preserves existing/cache TOV values.
VSLACK_CACHE_PATH = os.path.join(XLSX_DIR, "vslack_cache.csv")
PREPARED_SPEC_PATH = os.path.join(STUDY_RESULTS_DIR, "prepared_pscad_spec.csv")

PSCAD_INITIALISATION_OPTIONS = {
    "cache_path": VSLACK_CACHE_PATH,
    "vbase_kv": 275.0,
    "fbase_hz": 50.0,
    "system_base_mva": 100.0,
    # These bases are fallbacks only when the MW/MVAr columns are absent.
    "pbase_mw": 285.0,
    "qbase_mvar": 112.575,
    "update_cache": True,
    "verbose": True,
}

PSCAD_RUN_OPTIONS = {
    "model_dir": MODEL_DIR,
    "results_dir": STUDY_RESULTS_DIR,
    # project name, compiler, volley size and launch policy are intentionally TBD.
}


# -----------------------------------------------------------------------------
# RUN PSCAD ANALYSIS
# -----------------------------------------------------------------------------

RUN_ANALYSIS = False
ANALYSIS_EXTENSION = ".psout"  # also supports .pkl, .pickle or .csv

PSCAD_ANALYSIS_INPUTS = {
    "CSR": STUDY_RESULTS_DIR,
    "DMAT": STUDY_RESULTS_DIR,
    "DMAT_CRG": STUDY_RESULTS_DIR,
}
ANALYSIS_OUTPUTS_DIR = os.path.join(RESULTS_ROOT, "_analysis_results_{}".format(NOW_STR))

# Each selected name above receives one declarative job here.  Signal names,
# characteristic points and exact result folders are project content, so this
# list remains empty until the next instruction.  Available handler ids are
# printed by ``list_pscad_clause_handlers()`` when analysis is enabled.
#
# Example shape (do not enable until the real channel names are confirmed):
# {
#     "name": "MFRT",
#     "handler": "s5255_mfrt",
#     "inputs": [{"root": "CSR", "pattern": "CSR MFRT/*"}],
#     "options": {
#         "output_csv_path": "mfrt_results.csv",
#         "init_time_spec_key": "TIME_Full_Init_Time_sec",
#         "disturbance_command_spec_key": "Fault_Timing_Signal_sig",
#         "fault_type_command_spec_key": "Fault_Type_sig",
#         "vpoc_signal_name": "<confirm PSCAD channel>",
#     },
# }
PSCAD_ANALYSIS_JOBS = []

CONTINUE_ON_ANALYSIS_ERROR = True
STRICT_ANALYSIS_INPUTS = True
ANALYSIS_STATUS_PATH = None  # set a filename only when a JSON status file is wanted


# -----------------------------------------------------------------------------
# REPLOT PSCAD STUDIES
# -----------------------------------------------------------------------------

REPLOT_PSCAD = False
REPLOT_EXTENSION = ".psout"
PLOT_INPUTS_DIR = STUDY_RESULTS_DIR
PLOT_OUT_DIR = os.path.join(RESULTS_ROOT, "replots_{}".format(NOW_STR))
REMOVE_INIT_TIME = True

# Supply a project plotter implementing plot_from_df_and_dict after the PSCAD
# plot definitions and channel map have been confirmed.
PSCAD_REPLOTTER = None


# -----------------------------------------------------------------------------
# GENERATE APPENDICES
# -----------------------------------------------------------------------------

CREATE_APPENDIX = False
PLOT_RESULTS_DIRS = [STUDY_RESULTS_DIR]
OUTPUT_DIR_DMAT = RESULTS_ROOT
OUTPUT_DIR_CSR = RESULTS_ROOT
XLSX_PATHS, SHEETS_TO_PROCESS_COMBINED = spec_source_lists(SPEC_OPTIONS, "appendix")
ISSUED_DATE = "TBD"
REVISION_NO = "DRAFT"
OVERWRITE_TITLE = False
HARD_TITLE = "Appendix"
REPORT_NO = "004"
PSCAD_REPORT = False
CREATE_DISCHARGE_APPENDICES = True
CREATE_CHARGE_APPENDICES = True


# -----------------------------------------------------------------------------
# CREATE REPORT TABLES
# -----------------------------------------------------------------------------

CREATE_REPORT_TABLES = False
SPEC_PATHS_TABLES, SHEETS_TO_PROCESS_TABLES = spec_source_lists(SPEC_OPTIONS, "tables")
TABLE_DIR = str(PROJECT_ROOT / "002 report tables")
COLMAP_PATHS = [
    os.path.join(TABLE_DIR, "column_mapping_DMAT.csv"),
    os.path.join(TABLE_DIR, "column_mapping_CSR.csv"),
]
OUTPUT_DIRS_TABLE = [
    os.path.join(RESULTS_ROOT, "report_tables", "DMAT"),
    os.path.join(RESULTS_ROOT, "report_tables", "CSR"),
]


# -----------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    print("Native hbess_open package: {}".format(Path(hbess_open.__file__).resolve()))
    if SRC_DIR not in Path(hbess_open.__file__).resolve().parents:
        raise RuntimeError("hbess_open was not imported from this project's src directory")

    study_spec = None
    if PREPARE_PSCAD_SPEC or RUN_STUDIES:
        study_spec = load_spec_options(SPEC_OPTIONS)
        study_spec = prepare_pscad_spec(
            study_spec,
            use_vslack_cache=USE_VSLACK_CACHE,
            calc_tov_shunt_var=CALC_TOV_SHUNT_VAR,
            **PSCAD_INITIALISATION_OPTIONS,
        )

    if PREPARE_PSCAD_SPEC:
        Path(PREPARED_SPEC_PATH).parent.mkdir(parents=True, exist_ok=True)
        study_spec.to_csv(PREPARED_SPEC_PATH, index=False)
        print("Prepared PSCAD SPEC: {}".format(PREPARED_SPEC_PATH))

    if RUN_STUDIES:
        run_pscad_studies(spec=study_spec, **PSCAD_RUN_OPTIONS)

    if RUN_ANALYSIS:
        print("Available PSCAD handlers: {}".format(", ".join(list_pscad_clause_handlers())))
        run_analysis_pscad(
            ANALYSIS_TO_RUN=ANALYSIS_TO_RUN,
            ANALYSIS_JOBS=PSCAD_ANALYSIS_JOBS,
            INPUT_DIRS=PSCAD_ANALYSIS_INPUTS,
            OUTPUTS_DIR=ANALYSIS_OUTPUTS_DIR,
            extension=ANALYSIS_EXTENSION,
            continue_on_error=CONTINUE_ON_ANALYSIS_ERROR,
            strict_inputs=STRICT_ANALYSIS_INPUTS,
            status_path=ANALYSIS_STATUS_PATH,
        )

    if REPLOT_PSCAD:
        replot_pscad(
            extension=REPLOT_EXTENSION,
            replotter=PSCAD_REPLOTTER,
            PLOT_INPUTS_DIR=PLOT_INPUTS_DIR,
            PLOT_OUT_DIR=PLOT_OUT_DIR,
            x86=x86,
            remove_initialisation=REMOVE_INIT_TIME,
        )

    if CREATE_APPENDIX:
        create_appendix_heywoodbess(
            PLOT_RESULTS_DIRS=PLOT_RESULTS_DIRS,
            OUTPUT_DIR_DMAT=OUTPUT_DIR_DMAT,
            OUTPUT_DIR_CSR=OUTPUT_DIR_CSR,
            XLSX_PATHS=XLSX_PATHS,
            SHEETS_TO_PROCESS=SHEETS_TO_PROCESS_COMBINED,
            NOW_STR=NOW_STR,
            issued_date=ISSUED_DATE,
            revision_no=REVISION_NO,
            x86=PSCAD_REPORT,
            overwrite_title=OVERWRITE_TITLE,
            hard_title=HARD_TITLE,
            report_no=REPORT_NO,
            create_discharge_appendices=CREATE_DISCHARGE_APPENDICES,
            create_charge_appendices=CREATE_CHARGE_APPENDICES,
        )

    if CREATE_REPORT_TABLES:
        create_report_table_CSR_DMAT(
            COLMAP_PATHS=COLMAP_PATHS,
            SPEC_PATHS=SPEC_PATHS_TABLES,
            SHEETS_TO_PROCESS=SHEETS_TO_PROCESS_TABLES,
            OUTPUT_DIRS=OUTPUT_DIRS_TABLE,
            x86=x86,
        )
