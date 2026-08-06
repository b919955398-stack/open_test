from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

import pandas as pd

from hbess_open.open_psse.plot_adapter import invoke_project_plotter
from psse_open.commands import build_plan
from psse_open.config import ProjectConfig
from psse_open.definitions import load_or_build_project_config
from psse_open.engine import StudyEngine, write_plan
from psse_open.grid import impedance_from_fault_level, infinite_bus_voltage
from psse_open.models import Scenario
from psse_open.profiles import parse_signal_profile
from psse_open.progress import ConsoleReporter


INF_INIT_GRID_SCR = 3.68
INF_INIT_GRID_X2R = 5.0
INF_INIT_GRID_FL = 920.0

DEFAULT_SPEC_FIELDS_TO_PRINT = [
    "Spec_Source",
    "Sheet_Name",
    "Spec_Row",
    "Category",
    "Test No",
    "Subtest No",
    "File_Name",
    "Ppoc_MW_sig",
    "Qpoc_MVAr_init",
    "Vpoc_pu_sig",
    "Grid_SCR",
    "Grid_FL_MVA_sig",
    "Grid_X2R_sig",
    "Is_Infinite",
    "Post_Init_Duration_s",
    "Steps_per_write",
]


def _initial_numeric(value: Any, default: float = 0.0) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return float(default)
    if isinstance(value, str):
        profile = parse_signal_profile(value)
        if profile:
            return float(profile[0][1])
    return float(value)


def _load_config(model_dir: str) -> ProjectConfig:
    config = load_or_build_project_config(model_dir)
    config.data.setdefault("hooks_file", str(Path(__file__).resolve().parents[1] / "project_hooks.py"))
    return config


def get_vslacks(specification: pd.DataFrame, MODEL_DIR: str, slack_bus_num: int) -> pd.DataFrame:
    """Open replacement for the Pallet Initialiser-based Vslack pre-pass.

    Vslack is calculated analytically at the POC from the requested P/Q/V and
    Thevenin R/X. The actual run independently verifies and dispatches the case.
    The return shape intentionally matches the original helper: only rows whose
    PSSE Vslack expression contains `$VSLACK` are returned.
    """
    if "Vslack_pu_psse" not in specification.columns:
        print("no vgrid tests")
        return specification.iloc[0:0].copy()
    selected = specification[specification["Vslack_pu_psse"].astype(str).str.contains(r"\$VSLACK", na=False)].copy()
    if selected.empty:
        return selected
    config = _load_config(MODEL_DIR)
    bases = config.section("bases")
    replacements: List[str] = []
    for _index, row in selected.iterrows():
        vpoc = _initial_numeric(row.get("Vpoc_pu_sig"), bases.get("normal_v_pu", 1.0))
        p_mw = _initial_numeric(row.get("Ppoc_MW_sig"), _initial_numeric(row.get("Ppoc_pu")) * float(bases["p_mw"]))
        q_mvar = _initial_numeric(row.get("Qpoc_MVAr_init"), _initial_numeric(row.get("Qpoc_pu")) * float(bases.get("q_mvar", bases["p_mw"])))
        if str(row.get("Grid_SCR", "")).upper() == "ZERO_IMP":
            vslack = vpoc
        else:
            fault_level = _initial_numeric(row.get("Grid_FL_MVA_sig"))
            if fault_level <= 0:
                fault_level = _initial_numeric(row.get("Grid_SCR")) * float(bases["p_mw"])
            r_pu, x_pu = impedance_from_fault_level(fault_level, _initial_numeric(row.get("Grid_X2R_sig")))
            vslack = infinite_bus_voltage(vpoc, p_mw, q_mvar, r_pu, x_pu)
        replacements.append(str(row["Vslack_pu_psse"]).replace("$VSLACK", "{:.12g}".format(vslack)))
    selected.loc[:, "Vslack_pu_psse"] = replacements
    return selected


def _scenario_from_row(index: Any, row: pd.Series) -> Scenario:
    values = {}
    for key, value in row.to_dict().items():
        try:
            missing = bool(pd.isna(value))
        except (TypeError, ValueError):
            missing = False
        values[key] = None if missing else value
    return Scenario(
        sheet=str(values.get("Sheet_Name") or values.get("Category") or "SPEC"),
        row_number=int(index) + 2 if isinstance(index, int) else 0,
        file_name=str(values["File_Name"]),
        enabled=bool(values.get("PSSE", True)),
        values=values,
    )


def run_psse_studies(
    spec: pd.DataFrame,
    plotter: object,
    MODEL_DIR: str,
    RESULTS_DIR: str,
    plot_results: bool = True,
    keep_csv_results: bool = False,
    save_run_manifests: bool = False,
    keep_runtime_files: bool = False,
    keep_psse_logs: bool = False,
    psse_output_mode: str = None,
    verbose: bool = True,
    use_dispatch_cache: bool = True,
    dispatch_cache_dir: str = None,
    rebuild_dispatch_cache: bool = False,
    dispatch_key_columns: List[str] = None,
    auto_dispatch_key_columns: bool = True,
    verify_dispatch_cache_hashes: bool = False,
    progress_level: str = "commands",
    print_case_spec: bool = True,
    spec_fields_to_print: List[str] = None,
):
    """Run and immediately plot each completed PSS/E scenario.

    By default only OUT/JSON/PNG/PDF plus one root status file are retained.
    The CSV used by the plotter and the shared model runtime are temporary.
    """
    specification = spec.copy()
    if specification.empty:
        print("No PSS/E scenarios selected")
        return []
    specification["Is_Infinite"] = specification["Grid_SCR"].astype(str).str.upper() == "ZERO_IMP"
    infinite = specification["Is_Infinite"]
    specification.loc[infinite, "Grid_SCR"] = INF_INIT_GRID_SCR
    specification.loc[infinite, "Grid_X2R_sig"] = INF_INIT_GRID_X2R
    specification.loc[infinite, "Grid_FL_MVA_sig"] = INF_INIT_GRID_FL
    specification = specification[specification["PSSE"].fillna(False).astype(bool)]

    config = _load_config(MODEL_DIR)
    config.data["output_dir"] = str(Path(RESULTS_DIR).resolve())
    config.data["result_layout"] = "pallet"
    config.data["keep_runtime_files"] = bool(keep_runtime_files)
    config.data["keep_psse_logs"] = bool(keep_psse_logs)
    if psse_output_mode in (None, ""):
        effective_psse_output_mode = "files" if keep_psse_logs else "quiet"
    else:
        effective_psse_output_mode = str(psse_output_mode).strip().lower()
    if effective_psse_output_mode not in {"console", "files", "quiet"}:
        raise ValueError(
            "psse_output_mode must be console, files or quiet; got {!r}".format(psse_output_mode)
        )
    config.data["psse_output_mode"] = effective_psse_output_mode
    resolved_cache_dir = Path(dispatch_cache_dir).resolve() if dispatch_cache_dir else (
        Path(RESULTS_DIR).resolve().parent / "_dispatch_cache"
    )
    config.data["dispatch_cache"] = {
        "enabled": bool(use_dispatch_cache),
        "directory": str(resolved_cache_dir),
        "rebuild": bool(rebuild_dispatch_cache),
        "key_columns": list(dispatch_key_columns or []),
        "automatic_key_columns": bool(auto_dispatch_key_columns),
        "verify_hashes": bool(verify_dispatch_cache_hashes),
    }
    effective_progress_level = str(progress_level) if verbose else "quiet"
    reporter = ConsoleReporter(
        level=effective_progress_level,
        print_case_spec=bool(print_case_spec),
        spec_fields=(
            DEFAULT_SPEC_FIELDS_TO_PRINT
            if spec_fields_to_print is None
            else list(spec_fields_to_print)
        ),
    )
    config.data["progress"] = {
        "level": effective_progress_level,
        "print_case_spec": bool(print_case_spec),
        "spec_fields": reporter.spec_fields,
    }
    config.reporter = reporter
    config.data.setdefault("dynamics", {}).update({
        "iterations": 1000,
        "acceleration": 0.1,
        "tolerance": 0.0005,
        "time_step_s": 0.001,
        "frequency_filter_s": 0.016,
    })

    scenarios = [_scenario_from_row(index, row) for index, row in specification.iterrows()]
    plans = [build_plan(scenario) for scenario in scenarios]
    Path(RESULTS_DIR).mkdir(parents=True, exist_ok=True)
    category_source = (
        specification["Category"]
        if "Category" in specification.columns
        else specification.get("Sheet_Name", pd.Series(["SPEC"] * len(specification)))
    )
    category_counts = category_source.fillna("(blank)").astype(str).value_counts().to_dict()
    reporter.emit(
        "SPEC selected: {} scenarios | categories={}".format(
            len(specification), json.dumps(category_counts, sort_keys=True)
        ),
        "heading",
        "cases",
    )
    reporter.emit(
        "Dispatch cache: {} | rebuild={}".format(
            str(resolved_cache_dir), bool(rebuild_dispatch_cache)
        ),
        "dispatch",
        "cases",
    )
    reporter.emit(
        "Native PSS/E output: {}".format(effective_psse_output_mode),
        "heading",
        "cases",
    )
    if save_run_manifests:
        specification.to_csv(Path(RESULTS_DIR) / "running_spec.csv", index=False)
        write_plan(plans, str(Path(RESULTS_DIR) / "study_plan.json"))

    plot_failures = []

    def on_result(result, plan, number, total):
        name = result["file_name"]
        if result.get("status") != "completed":
            result["plot_status"] = "skipped_study_failed"
            if verbose:
                reporter.emit(
                    "[{}/{}] STUDY FAILED {}: {}".format(
                        number, total, name, result.get("error", "unknown error")
                    ),
                    "failure",
                    "cases",
                )
            return
        if verbose:
            reporter.emit(
                "[{}/{}] STUDY OK {} ({:.2f}s)".format(
                    number, total, name, float(result.get("elapsed_s", 0.0))
                ),
                "success",
                "cases",
            )
        csv_path = Path(result["csv"])
        if not plot_results:
            result["plot_status"] = "disabled"
            if not keep_csv_results:
                csv_path.unlink(missing_ok=True)
                result.pop("csv", None)
            if verbose:
                reporter.emit("[{}/{}] PLOT DISABLED {}".format(number, total, name), "warning", "cases")
            return
        result_dir = Path(result["out"]).parent
        png_path = result_dir / (name + ".png")
        pdf_path = result_dir / (name + ".pdf")
        try:
            invoke_project_plotter(plotter, str(csv_path), plan.scenario.values, str(result_dir))
            result.update(plot_status="completed", png=str(png_path), pdf=str(pdf_path))
            if not keep_csv_results:
                csv_path.unlink(missing_ok=True)
                result.pop("csv", None)
            if verbose:
                reporter.emit("[{}/{}] PLOT OK {}".format(number, total, png_path), "success", "cases")
        except Exception as exc:
            result.update(plot_status="failed", plot_error=str(exc))
            plot_failures.append((name, str(exc)))
            # Preserve the CSV only for a failed plot; it is the quickest way
            # to diagnose a chandef/plotter mismatch.
            if verbose:
                reporter.emit(
                    "[{}/{}] PLOT FAILED {}: {}".format(number, total, name, exc),
                    "failure",
                    "cases",
                )

    # StudyEngine invokes this callback before starting the next scenario.
    results = StudyEngine(config).run(plans, result_callback=on_result)

    status_path = Path(RESULTS_DIR) / "run_status.json"
    with open(status_path, "w", encoding="utf-8") as stream:
        json.dump(results, stream, indent=2, ensure_ascii=False)
    completed = sum(result.get("status") == "completed" for result in results)
    plotted = sum(result.get("plot_status") == "completed" for result in results)
    reporter.emit(
        "Run summary: {} completed, {} failed; {} plots created, {} plot failures".format(
            completed, len(results) - completed, plotted, len(plot_failures)
        ),
        "heading" if len(results) == completed and not plot_failures else "warning",
        "cases",
    )
    reporter.emit("Status file: {}".format(status_path), "heading", "cases")
    if results and completed == 0:
        raise RuntimeError("No PSS/E study completed, so no plots could be generated. See {}".format(status_path))
    if plot_failures:
        first_name, first_error = plot_failures[0]
        raise RuntimeError(
            "{} plot(s) failed; simulation OUT/CSV files were preserved. First failure {}: {}. See {}".format(
                len(plot_failures), first_name, first_error, status_path
            )
        )
    return results
