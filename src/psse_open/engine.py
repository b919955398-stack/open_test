from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import traceback
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from .backend import PsseBackend
from .bootstrap import import_psse
from .commands import build_plan
from .dispatch import DispatchCache, DispatchPlan, create_dispatch_plan
from .hooks import call_hook, load_hooks
from .models import Scenario, StudyPlan
from .output import out_to_csv
from .progress import ConsoleReporter


def _json_default(value):
    """Convert pandas/numpy scalar values without importing those packages."""
    if type(value).__name__ in {"NAType", "NaTType"}:
        return None
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError("Object of type {} is not JSON serializable".format(type(value).__name__))


def create_plans(scenarios: Iterable[Scenario]) -> List[StudyPlan]:
    return [build_plan(scenario) for scenario in scenarios]


def write_plan(plans: Iterable[StudyPlan], output: str) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as stream:
        json.dump([plan.as_dict() for plan in plans], stream, indent=2, ensure_ascii=False)
    return target


class StudyEngine:
    def __init__(self, config):
        self.config = config
        self.psspy, self.dyntools = import_psse(config.section("psse"))
        hooks_path = config.data.get("hooks_file")
        self.hooks = load_hooks(str(config.resolve(hooks_path))) if hooks_path else None
        self.backend = PsseBackend(self.psspy, config, self.hooks)
        self.reporter = getattr(config, "reporter", None) or ConsoleReporter.from_config(config)

    def _copy_inputs(self, work_dir: Path) -> tuple:
        files = self.config.section("files")
        sources = [self.config.resolve(files["sav"]), self.config.resolve(files["dyr"])]
        for pattern in files.get("copy_globs", ["*.dll", "*.txt", "*.cfg"]):
            sources.extend(self.config.base_dir.glob(pattern))
        seen = set()
        for source in sources:
            source = Path(source)
            if source in seen:
                continue
            seen.add(source)
            if not source.exists():
                raise FileNotFoundError("Required input does not exist: {}".format(source))
            shutil.copy2(str(source), str(work_dir / source.name))
        return work_dir / Path(files["sav"]).name, work_dir / Path(files["dyr"]).name

    def _console(self) -> ConsoleReporter:
        reporter = getattr(self, "reporter", None)
        if reporter is None:
            reporter = getattr(self.config, "reporter", None) or ConsoleReporter.from_config(self.config)
            self.reporter = reporter
        return reporter

    def _prepare_dispatch_cases(
        self,
        dispatch_plan: DispatchPlan,
        sav_path: Path,
        work_dir: Path,
    ) -> dict:
        settings = self.config.section("dispatch_cache")
        cache = DispatchCache(
            self.config,
            Path(settings["directory"]),
            rebuild=bool(settings.get("rebuild", False)),
            verify_hashes=bool(settings.get("verify_hashes", False)),
        )
        reporter = self._console()
        total_scenarios = len(dispatch_plan.assignments)
        total_groups = len(dispatch_plan.groups)
        reporter.emit(
            "{} selected scenarios -> {} unique initial operating conditions -> {} reused dispatches".format(
                total_scenarios, total_groups, max(0, total_scenarios - total_groups)
            ),
            "heading",
            "cases",
        )
        if dispatch_plan.extra_columns:
            reporter.emit(
                "Additional Dispatch Key columns: {}".format(", ".join(dispatch_plan.extra_columns)),
                "dispatch",
                "cases",
            )
        for number, group in enumerate(dispatch_plan.groups, start=1):
            reporter.emit(
                "PLAN [{}/{}] key={} cases={} representative={} | {}".format(
                    number,
                    total_groups,
                    group.short_key,
                    len(group.plans),
                    group.representative.scenario.file_name,
                    json.dumps(group.signature, sort_keys=True),
                ),
                "dispatch",
                "cases",
            )
        reporter.emit("Preparing missing dispatched SAV cases", "heading", "cases")
        states = {}
        built = 0
        hits = 0
        failed = 0
        previous_cwd = Path.cwd()

        for number, group in enumerate(dispatch_plan.groups, start=1):
            representative = group.representative.scenario
            prefix = "[{}/{}] key={} cases={} representative={}".format(
                number, total_groups, group.short_key, len(group.plans), representative.file_name
            )
            cached = cache.cached_path(group)
            if cached is not None:
                states[group.key] = {"status": "completed", "cache_status": "hit", "path": str(cached)}
                hits += 1
                reporter.emit(prefix + " CACHE HIT " + str(cached), "success", "cases")
                continue

            temporary = cache.temporary_path(group)
            target = cache.target_path(group)
            started = time.perf_counter()
            try:
                reporter.emit(prefix + " BUILD", "dispatch", "cases")
                reporter.case_spec(representative.values, prefix + " SPEC")
                os.chdir(str(work_dir))
                reporter.emit(prefix + " LOAD BASE SAV " + str(sav_path), "load", "commands")
                self.backend.initialize(sav_path, work_dir / ("dispatch_" + group.short_key))
                call_hook(self.hooks, "before_dispatch", self.backend, representative, work_dir)
                reporter.command(prefix, "CONFIGURE GRID", {
                    "fault_level_mva": group.signature["fault_level_mva"],
                    "x_over_r": group.signature["grid_x_over_r"],
                })
                r_pu, x_pu = self.backend.configure_grid(representative)
                reporter.command(prefix, "DISPATCH P/Q/V", {
                    "p_mw": group.signature["p_target_mw"],
                    "q_mvar": group.signature["q_target_mvar"],
                    "vpoc_pu": group.signature["vpoc_pu"],
                })
                self.backend.dispatch(representative, r_pu, x_pu)
                if bool(group.signature["is_infinite"]):
                    reporter.command(prefix, "MAKE GRID INFINITE")
                    self.backend.make_grid_infinite()
                call_hook(self.hooks, "after_dispatch", self.backend, representative, work_dir)
                reporter.emit(prefix + " SAVE DISPATCHED SAV " + str(target), "load", "commands")
                self.backend.save_case(temporary)
                cache.publish(temporary, target)
                cache.record_success(group, target)
                elapsed = time.perf_counter() - started
                states[group.key] = {
                    "status": "completed",
                    "cache_status": "built",
                    "path": str(target),
                    "elapsed_s": round(elapsed, 3),
                }
                built += 1
                reporter.emit(prefix + " BUILT in {:.2f}s".format(elapsed), "success", "cases")
            except Exception as exc:
                elapsed = time.perf_counter() - started
                error_traceback = traceback.format_exc()
                states[group.key] = {
                    "status": "failed",
                    "cache_status": "failed",
                    "error": str(exc),
                    "traceback": error_traceback,
                    "elapsed_s": round(elapsed, 3),
                }
                failed += 1
                try:
                    cache.record_failure(group, str(exc))
                except Exception:
                    pass
                reporter.emit(prefix + " FAILED: " + str(exc), "failure", "cases")
            finally:
                self.backend.halt()
                os.chdir(str(previous_cwd))
                if temporary.exists():
                    temporary.unlink()

        reporter.emit(
            "Dispatch preparation complete: {} cache hits, {} built, {} failed; cache={}".format(
                hits, built, failed, cache.directory
            ),
            "heading" if failed == 0 else "warning",
            "cases",
        )
        return states

    def run(
        self,
        plans: Iterable[StudyPlan],
        result_callback: Optional[Callable[[dict, StudyPlan, int, int], None]] = None,
    ) -> List[dict]:
        """Run scenarios sequentially and publish each result immediately.

        Model inputs are staged once in a shared temporary runtime directory,
        instead of being copied into one permanent ``_work`` directory per
        scenario. ``result_callback`` runs after each PSS/E case is halted, so
        callers can plot that case before the next simulation starts.
        """
        plans = list(plans)
        output_root = self.config.resolve(self.config.data.get("output_dir", "outputs"))
        output_root.mkdir(parents=True, exist_ok=True)
        results: List[dict] = []
        continue_on_error = bool(self.config.data.get("continue_on_error", True))
        keep_runtime = bool(self.config.data.get("keep_runtime_files", False))
        dispatch_settings = self.config.section("dispatch_cache")
        use_dispatch_cache = bool(dispatch_settings.get("enabled", False))
        reporter = self._console()
        if keep_runtime:
            work_dir = output_root / "_runtime"
            work_dir.mkdir(parents=True, exist_ok=True)
        else:
            work_dir = Path(tempfile.mkdtemp(prefix="hbess_psse_"))

        try:
            sav_path, dyr_path = self._copy_inputs(work_dir)
            dispatch_plan = None
            dispatch_states = {}
            if use_dispatch_cache:
                dispatch_plan = create_dispatch_plan(
                    plans,
                    self.config,
                    explicit_columns=dispatch_settings.get("key_columns", []),
                    automatic_columns=bool(dispatch_settings.get("automatic_key_columns", True)),
                )
                dispatch_states = self._prepare_dispatch_cases(dispatch_plan, sav_path, work_dir)

            total = len(plans)
            for number, plan in enumerate(plans, start=1):
                prefix = "[{}/{}] {}".format(number, total, plan.scenario.file_name)
                pallet_layout = self.config.data.get("result_layout") == "pallet"
                result_dir = output_root / plan.scenario.category if pallet_layout else output_root / "csv"
                result_dir.mkdir(parents=True, exist_ok=True)
                out_path = result_dir / (plan.scenario.file_name + ".out")
                csv_path = result_dir / (plan.scenario.file_name + ".csv")
                json_path = result_dir / (plan.scenario.file_name + ".json")
                if bool(self.config.data.get("keep_scenario_json", True)):
                    with open(json_path, "w", encoding="utf-8") as stream:
                        json.dump(
                            plan.scenario.values,
                            stream,
                            indent=2,
                            ensure_ascii=False,
                            allow_nan=False,
                            default=_json_default,
                        )

                assignment = dispatch_plan.assignments[number - 1] if dispatch_plan is not None else None
                dispatch_state = dispatch_states.get(assignment.key) if assignment is not None else None
                result = {"file_name": plan.scenario.file_name, "status": "running"}
                if assignment is not None:
                    result["dispatch_key"] = assignment.short_key
                    result["dispatch_cache_status"] = (
                        dispatch_state.get("cache_status") if dispatch_state else "missing"
                    )
                    if dispatch_state and dispatch_state.get("path"):
                        result["dispatched_sav"] = dispatch_state["path"]
                if keep_runtime:
                    result["work_dir"] = str(work_dir)

                reporter.emit(prefix + " START", "heading", "cases")
                reporter.case_spec(plan.scenario.values, prefix + " SPEC")
                if assignment is not None:
                    reporter.emit(
                        prefix + " DISPATCH KEY {} ({})".format(
                            assignment.short_key,
                            dispatch_state.get("cache_status", "missing") if dispatch_state else "missing",
                        ),
                        "dispatch",
                        "cases",
                    )

                previous_cwd = Path.cwd()
                stop_after_case = False
                started = time.perf_counter()
                try:
                    if assignment is not None and (
                        dispatch_state is None or dispatch_state.get("status") != "completed"
                    ):
                        dispatch_error = (
                            dispatch_state.get("error", "dispatch case is unavailable")
                            if dispatch_state else "dispatch case was not prepared"
                        )
                        raise RuntimeError(
                            "Dispatch preparation failed for key {}: {}".format(
                                assignment.short_key, dispatch_error
                            )
                        )

                    os.chdir(str(work_dir))
                    call_hook(self.hooks, "before_case", self.backend, plan.scenario, work_dir)
                    if assignment is not None:
                        dynamic_sav = Path(dispatch_state["path"])
                        reporter.emit(prefix + " LOAD DISPATCHED SAV " + str(dynamic_sav), "load", "commands")
                        self.backend.initialize(
                            dynamic_sav,
                            work_dir / plan.scenario.file_name,
                            solve_load_flow=False,
                        )
                        self.backend.configure_scenario_options(plan.scenario)
                    else:
                        reporter.emit(prefix + " LOAD BASE SAV " + str(sav_path), "load", "commands")
                        self.backend.initialize(sav_path, work_dir / plan.scenario.file_name)
                        self.backend.configure_scenario_options(plan.scenario)
                        reporter.command(prefix, "CONFIGURE GRID")
                        r_pu, x_pu = self.backend.configure_grid(plan.scenario)
                        reporter.command(prefix, "DISPATCH P/Q/V")
                        self.backend.dispatch(plan.scenario, r_pu, x_pu)
                        if bool(plan.scenario.get("Is_Infinite", False)):
                            reporter.command(prefix, "MAKE GRID INFINITE")
                            self.backend.make_grid_infinite()
                        call_hook(self.hooks, "after_dispatch", self.backend, plan.scenario, work_dir)

                    reporter.emit(prefix + " DYNAMIC INIT " + str(dyr_path), "load", "commands")
                    self.backend.initialize_dynamics(work_dir, dyr_path, out_path, plan.playback)
                    call_hook(self.hooks, "after_dynamic_initialization", self.backend, plan.scenario, work_dir)
                    current_time = 0.0
                    for event in plan.events:
                        if event.time < current_time:
                            raise RuntimeError("Events are not time ordered")
                        if event.time > current_time:
                            reporter.emit(
                                prefix + " RUN {:.6g} -> {:.6g} s".format(current_time, event.time),
                                "load",
                                "commands",
                            )
                            self.backend.run_to(event.time)
                            current_time = event.time
                        reporter.command(
                            prefix,
                            "t={:.6g}s {}".format(event.time, event.kind.upper().replace("_", " ")),
                            dict(event.parameters, source=event.source),
                        )
                        self.backend.apply_event(event, plan.scenario)
                    if plan.scenario.end_time > current_time:
                        reporter.emit(
                            prefix + " RUN {:.6g} -> {:.6g} s".format(
                                current_time, plan.scenario.end_time
                            ),
                            "load",
                            "commands",
                        )
                        self.backend.run_to(plan.scenario.end_time)
                    reporter.emit(prefix + " CONVERT OUT -> CSV", "load", "commands")
                    out_to_csv(
                        str(out_path), str(csv_path), self.dyntools,
                        self.config.section("dynamics").get("frequency_hz", 50.0),
                    )
                    result.update(
                        status="completed",
                        out=str(out_path),
                        csv=str(csv_path),
                        elapsed_s=round(time.perf_counter() - started, 3),
                    )
                    if json_path.exists():
                        result["json"] = str(json_path)
                except Exception as exc:
                    result.update(
                        status="failed",
                        error=str(exc),
                        traceback=traceback.format_exc(),
                        elapsed_s=round(time.perf_counter() - started, 3),
                    )
                    failure_path = result_dir / (plan.scenario.file_name + "_FAILED.txt")
                    with open(failure_path, "w", encoding="utf-8") as stream:
                        stream.write(result["traceback"])
                    result["failure_log"] = str(failure_path)
                    stop_after_case = not continue_on_error
                    reporter.emit(prefix + " FAILED: " + str(exc), "failure", "cases")
                finally:
                    self.backend.halt()
                    os.chdir(str(previous_cwd))

                results.append(result)
                if result_callback is not None:
                    result_callback(result, plan, number, total)
                with open(output_root / "run_status.json", "w", encoding="utf-8") as stream:
                    json.dump(results, stream, indent=2, default=_json_default)
                if stop_after_case:
                    break
        finally:
            self.backend.halt()
            if not keep_runtime:
                shutil.rmtree(str(work_dir), ignore_errors=True)
        return results
