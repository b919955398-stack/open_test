from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any, List
import time

import pandas as pd

from hbess_open.open_psse.plot_adapter import (
    downsample_dataframe_for_plot,
    invoke_project_plotter_from_dataframe,
)
from psse_open.commands import build_plan
from psse_open.config import ProjectConfig
from psse_open.definitions import load_or_build_project_config
from psse_open.engine import StudyEngine, write_plan
from psse_open.grid import impedance_from_fault_level, infinite_bus_voltage
from psse_open.models import Scenario
from psse_open.profiles import parse_signal_profile
from psse_open.progress import ConsoleReporter
from psse_open.output import write_dataframe_csv


_NATIVE_STUDY_ENGINE_CLASS = StudyEngine


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

# Add a project-specific steady-state column here only when a dispatch hook
# reads it and its name is not covered by the automatic detector.
DEFAULT_DISPATCH_KEY_COLUMNS = []


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


def _plan_transition_times(plan) -> list:
    events = list(getattr(plan, "events", []) or [])
    playback = list(getattr(plan, "playback", []) or [])
    return sorted(
        {
            float(item.time)
            for item in events + playback
        }
    )


def _source_fingerprint(value) -> dict:
    if value is None:
        return {"type": "none"}
    target = value if inspect.isfunction(value) else type(value)
    path = inspect.getsourcefile(target)
    result = {
        "module": getattr(target, "__module__", ""),
        "name": getattr(target, "__qualname__", getattr(target, "__name__", "")),
    }
    if path and Path(path).is_file():
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        result.update(file=Path(path).name, sha256=digest)
    return result


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
    keep_result_dyr: bool = True,
    keep_initialised_sav: bool = True,
    psse_output_mode: str = "console",
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
    plot_in_background: bool = True,
    max_pending_plots: int = 1,
    max_plot_points: int = 20000,
    resume_completed: bool = True,
):
    """Run and immediately plot each completed PSS/E scenario.

    By default each completed scenario retains the established Pallet-style
    DYR/JSON/OUT/PDF/PNG/initialised-SAV result set plus one root status file.
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
    config.data["keep_result_dyr"] = bool(keep_result_dyr)
    config.data["keep_initialised_sav"] = bool(keep_initialised_sav)
    config.data["keep_csv_results"] = bool(keep_csv_results)
    config.data["in_memory_postprocessing"] = True
    config.data["resume_completed_results"] = bool(resume_completed)
    config.data["resume_require_plots"] = bool(plot_results)
    config.data["result_postprocessing"] = {
        "plot_results": bool(plot_results),
        "max_plot_points": int(max_plot_points or 0),
        "plotter": _source_fingerprint(plotter),
        "pre_process_fn": _source_fingerprint(
            getattr(plotter, "pre_process_fn", None)
        ),
    }
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
        "key_columns": list(
            DEFAULT_DISPATCH_KEY_COLUMNS
            if dispatch_key_columns is None
            else dispatch_key_columns
        ),
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
    pending_jobs = []
    worker_enabled = bool(plot_results and plot_in_background)
    executor = ThreadPoolExecutor(max_workers=1) if worker_enabled else None
    pending_limit = max(1, int(max_pending_plots or 1))

    def postprocess_case(result, plan, dataframe=None):
        started = time.perf_counter()
        name = result["file_name"]
        result_dir = Path(result["out"]).parent
        csv_path = result_dir / (name + ".csv")
        png_path = result_dir / (name + ".png")
        pdf_path = result_dir / (name + ".pdf")
        if plot_results:
            # A rerun must never publish plots left by an older fingerprint.
            # Remove them before rendering so a plot failure cannot leave a
            # stale PNG/PDF that appears to belong to the current result.
            png_path.unlink(missing_ok=True)
            pdf_path.unlink(missing_ok=True)
        dataframe = dataframe if dataframe is not None else result.get("_dataframe")
        if dataframe is None:
            existing_csv = result.get("csv")
            if not existing_csv:
                return {
                    "plot_status": "failed",
                    "plot_error": "Completed study has neither in-memory OUT data nor CSV",
                    "timings_s": {"postprocess_total": 0.0},
                }
            dataframe = pd.read_csv(existing_csv)

        outcome = {"timings_s": {}}
        if not plot_results:
            outcome["plot_status"] = "disabled"
            if keep_csv_results and not csv_path.exists():
                csv_started = time.perf_counter()
                write_dataframe_csv(dataframe, str(csv_path))
                outcome["csv"] = str(csv_path)
                outcome["timings_s"]["csv_write"] = round(
                    time.perf_counter() - csv_started, 6
                )
            elif not keep_csv_results:
                csv_path.unlink(missing_ok=True)
                outcome["_remove_csv"] = True
            outcome["timings_s"]["postprocess_total"] = round(
                time.perf_counter() - started, 6
            )
            return outcome

        try:
            downsample_started = time.perf_counter()
            plot_frame = downsample_dataframe_for_plot(
                dataframe,
                max_points=max_plot_points,
                event_times=_plan_transition_times(plan),
            )
            outcome["plot_points"] = {
                "source": len(dataframe),
                "rendered": len(plot_frame),
            }
            outcome["timings_s"]["plot_downsample"] = round(
                time.perf_counter() - downsample_started, 6
            )
            plot_started = time.perf_counter()
            created = invoke_project_plotter_from_dataframe(
                plotter,
                plot_frame,
                plan.scenario.values,
                str(result_dir),
                source_description=str(result["out"]),
            )
            if not created:
                raise RuntimeError(
                    "Plotter does not provide plot_from_df_and_dict"
                )
            outcome.update(
                plot_status="completed", png=str(png_path), pdf=str(pdf_path)
            )
            outcome["timings_s"]["plot"] = round(
                time.perf_counter() - plot_started, 6
            )
            if keep_csv_results:
                outcome["csv"] = str(csv_path)
            else:
                csv_path.unlink(missing_ok=True)
                outcome["_remove_csv"] = True
        except Exception as exc:
            # Preserve a diagnostic CSV when plotting fails.
            write_dataframe_csv(dataframe, str(csv_path))
            outcome.update(
                plot_status="failed", plot_error=str(exc), csv=str(csv_path)
            )
        outcome["timings_s"]["postprocess_total"] = round(
            time.perf_counter() - started, 6
        )
        return outcome

    def apply_outcome(result, outcome, number, total):
        name = result["file_name"]
        timing_updates = outcome.pop("timings_s", {})
        if outcome.pop("_remove_csv", False):
            result.pop("csv", None)
        result.setdefault("timings_s", {}).update(timing_updates)
        result.update(outcome)
        if result.get("plot_status") == "completed":
            reporter.emit(
                "[{}/{}] PLOT OK {} ({:.2f}s, {}/{})".format(
                    number,
                    total,
                    result.get("png"),
                    float(result.get("timings_s", {}).get("plot", 0.0)),
                    result.get("plot_points", {}).get("rendered", 0),
                    result.get("plot_points", {}).get("source", 0),
                ),
                "success",
                "cases",
            )
        elif result.get("plot_status") == "failed":
            plot_failures.append((name, result.get("plot_error", "unknown error")))
            reporter.emit(
                "[{}/{}] PLOT FAILED {}: {}".format(
                    number, total, name, result.get("plot_error")
                ),
                "failure",
                "cases",
            )

    def drain_oldest():
        future, result, number, total = pending_jobs.pop(0)
        try:
            outcome = future.result()
        except Exception as exc:
            outcome = {"plot_status": "failed", "plot_error": str(exc)}
        apply_outcome(result, outcome, number, total)

    def on_result(result, plan, number, total):
        name = result["file_name"]
        if result.get("status") != "completed":
            result["plot_status"] = "skipped_study_failed"
            reporter.emit(
                "[{}/{}] STUDY FAILED {}: {}".format(
                    number, total, name, result.get("error", "unknown error")
                ),
                "failure",
                "cases",
            )
            return
        if result.get("resume_status") == "hit":
            result["plot_status"] = "reused"
            reporter.emit(
                "[{}/{}] RESUME OK {}".format(number, total, name),
                "success",
                "cases",
            )
            return
        reporter.emit(
            "[{}/{}] STUDY OK {} ({:.2f}s)".format(
                number, total, name, float(result.get("elapsed_s", 0.0))
            ),
            "success",
            "cases",
        )
        dataframe = result.get("_dataframe")
        if executor is None:
            apply_outcome(
                result,
                postprocess_case(result, plan, dataframe),
                number,
                total,
            )
            return
        while len(pending_jobs) >= pending_limit:
            drain_oldest()
        result["plot_status"] = "queued"
        pending_jobs.append(
            (
                executor.submit(postprocess_case, result, plan, dataframe),
                result,
                number,
                total,
            )
        )

    batch_started = time.perf_counter()
    try:
        # Callback submits plotting work and returns, allowing PSS/E to start the
        # next case while the single background worker renders the previous one.
        results = StudyEngine(config).run(plans, result_callback=on_result)
        while pending_jobs:
            drain_oldest()
    finally:
        if executor is not None:
            executor.shutdown(wait=True)
    batch_elapsed = time.perf_counter() - batch_started

    for result, plan in zip(results, plans):
        json_value = result.get("json")
        fingerprint = result.get("result_fingerprint")
        if not json_value or not fingerprint:
            continue
        complete = (
            result.get("status") == "completed"
            and (
                not plot_results
                or result.get("plot_status") in {"completed", "reused"}
            )
        )
        _NATIVE_STUDY_ENGINE_CLASS._write_result_metadata(
            Path(json_value),
            plan.scenario.values,
            fingerprint,
            "completed" if complete else "failed",
            plot_status=result.get("plot_status"),
            error=(
                result.get("error")
                or result.get("plot_error")
            ),
        )

    status_path = Path(RESULTS_DIR) / "run_status.json"
    with open(status_path, "w", encoding="utf-8") as stream:
        json.dump(results, stream, indent=2, ensure_ascii=False)
    completed = sum(result.get("status") == "completed" for result in results)
    plotted = sum(result.get("plot_status") == "completed" for result in results)
    resumed = sum(result.get("resume_status") == "hit" for result in results)
    reporter.emit(
        "Run summary: {} completed, {} failed; {} resumed, {} plots created, "
        "{} plot failures; {:.2f}s total".format(
            completed,
            len(results) - completed,
            resumed,
            plotted,
            len(plot_failures),
            batch_elapsed,
        ),
        "heading"
        if len(results) == completed and not plot_failures
        else "warning",
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
