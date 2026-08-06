"""Heywood BESS master script using the open/native PSS/E runner.

The layout intentionally follows the supplied company master: clause choices,
study settings, analysis, replotting, appendices, report tables, then one main
entry point. Only the PSS/E automation layer has been replaced.
"""

import os
import sys
from pathlib import Path

# -----------------------------------------------------------------------------
# LOCAL PACKAGE PRIORITY
# -----------------------------------------------------------------------------

# Prefer this project's ``src`` tree over any old editable installation.
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import hbess_open
import psse_open
from hbess_open.open_psse.specs import load_spec_options, now_str, spec_source_lists
from hbess_open.plotting.hbess_psse_plotter import HbessPssePlotter
from hbess_open.plotting.process_and_calc_psse import pre_process_dataframe
from hbess_open.studyrunners.psse_study_runner import get_vslacks, run_psse_studies

from hbess_open.analysis.run_analysis_psse import run_analysis_psse
from hbess_open.appendices.create_appendix import create_appendix_heywoodbess
from hbess_open.plotting.replotters import replot_psse
from hbess_open.report_tables.create_report_tables_spec import create_report_table_CSR_DMAT


# -----------------------------------------------------------------------------
# CLAUSES
# -----------------------------------------------------------------------------

x86 = True
NOW_STR = now_str()
APPENDIX_PROJECT_NAME = "Heywood BESS"

SHEETS_TO_PROCESS_CSR = [
    # "5253_F",
    # "5254_Withstand",
    # "5254_CUO",
    # "5255_TOV",
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
    # "5255_BalFaults_DD_R2",
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
    # "Vdroop characteristic",
    # "Vgrid step analysis",
    # "Vref step analysis",
    # "Qref step analysis",
    # "PFref step analysis",
    # "S5258 Active Power Reduction",
    # "diq/dV characteristic",
    # "IQ Rise Settle & P Recovery Curve",
    # "Frequency ride-through characteristic",
    # "Voltage ride-through characteristic",
]


# -----------------------------------------------------------------------------
# RUN SETTINGS + PATHS
# -----------------------------------------------------------------------------

SAV_VERSION = "v0-0-4"
DYR_VERSION = "v0-0-4"

XLSX_DIR = r"C:\Users\AlvinBai\Grid-Link\Projects - Documents\Atmos\Heywood BESS R0\02_Deliverables\PROJECT_SPEC"
XLSX_PATH_CSR = os.path.join(XLSX_DIR, "HY_Spec_CSR_300.xlsx")
XLSX_PATH_DMAT = os.path.join(XLSX_DIR, "HY_Spec_DMAT.xlsx")
XLSX_PATH_DMAT_CRG = os.path.join(XLSX_DIR, "HY_Spec_DMAT_CRG.xlsx")
XLSX_PATH_DMAT_FLATRUN = os.path.join(XLSX_DIR, "HY_Spec_FLATTEST.xlsx")

MODEL_DIR = r"C:\Grid\WorkFolder\Heywood work folder\open test\psse model"
RESULTS_ROOT = r"C:\Grid\WorkFolder\Heywood work folder\open test"
RESULTS_DIR = os.path.join(
    RESULTS_ROOT,
    "{}_sav_{}_dyr".format(SAV_VERSION, DYR_VERSION),
    NOW_STR,
)
SLACK_BUS_NUM = 331182


# -----------------------------------------------------------------------------
# SPEC OPTIONS — the single source of truth for every workflow
# -----------------------------------------------------------------------------

SPEC_OPTIONS = {
    "sources": [
        {
            "name": "CSR",
            "path": XLSX_PATH_CSR,
            "sheets": SHEETS_TO_PROCESS_CSR,  # exact names or e.g. ["5255_*", "!5255_*_OLD"]
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
            "name": "FLATRUN",
            "path": XLSX_PATH_DMAT_FLATRUN,
            "sheets": SHEETS_TO_PROCESS_FLATRUN,
            "enabled": True,
            "workflows": ["studies"],
        },
    ],
    "enabled_only": True,                 # accepts True/False, 1/0, yes/no, on/off
    "enabled_column": "PSSE",
    "filters": {
        # "Test No": {"==": 1},          # or simply "<= 12"
        # "Subtest No": {"==": 5},
        # "Batch": {"==": 2},
    },
    "include_categories": [],             # glob examples: ["*Fault*", "Fgrid"]
    "exclude_categories": [],
    "include_file_names": [],             # glob examples: ["HY_52511_*"]
    "exclude_file_names": [],
    "text_filter": None,                  # searches every text column
    "limit": None,                        # e.g. 3 for a quick smoke test
    "strict_sheets": True,                # typo/missing sheet raises a useful error
    "duplicate_policy": "error",          # error | first | last | allow
}


# -----------------------------------------------------------------------------
# RUN PSS/E STUDIES
# -----------------------------------------------------------------------------

RUN_STUDIES = True
PLOT_RESULTS = True              # plotted immediately after each completed case
KEEP_CSV_RESULTS = False         # temporary CSV is removed after a successful plot
SAVE_RUN_MANIFESTS = False       # running_spec.csv and study_plan.json
KEEP_RUNTIME_FILES = False       # one shared temporary runtime, not _work/<case>
KEEP_PSSE_LOGS = False           # progress/alert logs are normally unnecessary
VERBOSE_RUN_STATUS = True


def build_study_spec():
    """Load selected sheets and retain the original Vslack workflow."""
    specification = load_spec_options(SPEC_OPTIONS)

    vslack_spec = get_vslacks(specification, MODEL_DIR, SLACK_BUS_NUM)
    specification.update(vslack_spec)
    return specification.reset_index(drop=True)


# -----------------------------------------------------------------------------
# RUN ANALYSIS
# -----------------------------------------------------------------------------

RUN_ANALYSIS = False

if RUN_STUDIES:
    DEFAULT_ANALYSIS_INPUTS_DIR = RESULTS_DIR
else:
    DEFAULT_ANALYSIS_INPUTS_DIR = r"D:\results\heywoodbess\psse\EXISTING_RUN"

CSR_INPUTS_DIR = DEFAULT_ANALYSIS_INPUTS_DIR
ANALYSIS_EXTENSION = ".out"
ANALYSIS_OUTPUTS_DIR = os.path.join(CSR_INPUTS_DIR, "_analysis_{}".format(NOW_STR))

DPDF_CHARACTERISTIC_POINTS = [
    (-6, 570),
    (-1.715, 570),
    (-0.865, 285),
    (-0.1, 11.4),
    (-0.015, 0),
    (0.015, 0),
    (0.1, -11.4),
    (0.865, -285),
    (1.715, -570),
    (6, -570),
]

VDROOP_CHARACTERISTIC_POINTS = [
    (-0.1, 112.575),
    (-0.04, 112.575),
    (0.04, -112.575),
    (0.1, -112.575),
]

HVRT_THRESHOLDS = [
    {"value": 1.15, "withstand_sec": 60, "colour": "yellow"},
    {"value": 1.25, "withstand_sec": 1, "colour": "orange"},
]

LVRT_THRESHOLDS = [
    {"value": 0.8, "withstand_sec": 21, "colour": "yellow"},
    {"value": 0.4, "withstand_sec": 21, "colour": "red"},
]


# -----------------------------------------------------------------------------
# REPLOT PSS/E STUDIES
# -----------------------------------------------------------------------------

REPLOT_PSSE = False
REPLOT_EXTENSION = ".out"
PLOT_INPUTS_DIR = r"D:\results\heywoodbess\psse\EXISTING_RUN"
PLOT_OUT_DIR = os.path.join(PLOT_INPUTS_DIR, "replots")


# -----------------------------------------------------------------------------
# GENERATE APPENDICES
# -----------------------------------------------------------------------------

CREATE_APPENDIX = False

PLOT_RESULTS_DIRS = [RESULTS_DIR]
OUTPUT_DIR_DMAT = RESULTS_DIR
OUTPUT_DIR_CSR = RESULTS_DIR
XLSX_PATHS, SHEETS_TO_PROCESS_COMBINED = spec_source_lists(SPEC_OPTIONS, "appendix")
ISSUED_DATE = "20th July 2026"
REVISION_NO = "DRAFT"
OVERWRITE_TITLE = False
HARD_TITLE = "Appendix"
REPORT_NO = "004"
PSSE_REPORT = True
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
    print("Native psse_open engine: {}".format(Path(psse_open.__file__).resolve()))
    if SRC_DIR not in Path(hbess_open.__file__).resolve().parents:
        raise RuntimeError("hbess_open was not imported from this project's src directory")

    if RUN_STUDIES:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        spec = build_study_spec()
        plotter = HbessPssePlotter(pre_process_fn=pre_process_dataframe)
        run_psse_studies(
            spec=spec,
            plotter=plotter,
            MODEL_DIR=MODEL_DIR,
            RESULTS_DIR=RESULTS_DIR,
            plot_results=PLOT_RESULTS,
            keep_csv_results=KEEP_CSV_RESULTS,
            save_run_manifests=SAVE_RUN_MANIFESTS,
            keep_runtime_files=KEEP_RUNTIME_FILES,
            keep_psse_logs=KEEP_PSSE_LOGS,
            verbose=VERBOSE_RUN_STATUS,
        )

    if RUN_ANALYSIS:
        run_analysis_psse(
            x86=x86,
            extension=ANALYSIS_EXTENSION,
            ANALYSIS_TO_RUN=ANALYSIS_TO_RUN,
            DPDF_CHARACTERISTIC_POINTS=DPDF_CHARACTERISTIC_POINTS,
            VDROOP_CHARACTERISTIC_POINTS=VDROOP_CHARACTERISTIC_POINTS,
            HVRT_THRESHOLDS=HVRT_THRESHOLDS,
            LVRT_THRESHOLDS=LVRT_THRESHOLDS,
            CSR_INPUTS_DIR=CSR_INPUTS_DIR,
            OUTPUTS_DIR=ANALYSIS_OUTPUTS_DIR,
        )

    if REPLOT_PSSE:
        replotter = HbessPssePlotter(pre_process_fn=pre_process_dataframe)
        replot_psse(
            extension=REPLOT_EXTENSION,
            replotter=replotter,
            PLOT_INPUTS_DIR=PLOT_INPUTS_DIR,
            PLOT_OUT_DIR=PLOT_OUT_DIR,
            x86=x86,
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
            x86=PSSE_REPORT,
            overwrite_title=OVERWRITE_TITLE,
            hard_title=HARD_TITLE,
            report_no=REPORT_NO,
            create_discharge_appendices=CREATE_DISCHARGE_APPENDICES,
            create_charge_appendices=CREATE_CHARGE_APPENDICES,
        )

    if CREATE_REPORT_TABLES:
        for output_dir in OUTPUT_DIRS_TABLE:
            os.makedirs(output_dir, exist_ok=True)
        create_report_table_CSR_DMAT(
            COLMAP_PATHS=COLMAP_PATHS,
            SPEC_PATHS=SPEC_PATHS_TABLES,
            SHEETS_TO_PROCESS=SHEETS_TO_PROCESS_TABLES,
            OUTPUT_DIRS=OUTPUT_DIRS_TABLE,
            x86=x86,
        )
