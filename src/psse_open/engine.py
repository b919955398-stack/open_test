from __future__ import annotations

import json
import hashlib
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
from .output import out_to_csv, out_to_dataframe, write_dataframe_csv
from .progress import ConsoleReporter


RESULT_METADATA_KEY = "_native_run"
RESULT_METADATA_SCHEMA_VERSION = 1
RESULT_ALGORITHM_VERSION = "native-psse-result-v1.8.0"


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _stable_json_bytes(value) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=_json_default,
    ).encode("utf-8")


def _publish_by_move(source: Path, target: Path) -> None:
    """Publish a staged result without copying when both paths share a volume."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(str(source), str(target))
    except OSError:
        shutil.copy2(str(source), str(target))
        source.unlink(missing_ok=True)


def _publish_by_link(source: Path, target: Path) -> None:
    """Hard-link immutable input data into results, with a portable copy fallback."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    try:
        os.link(str(source), str(target))
    except OSError:
        shutil.copy2(str(source), str(target))


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

    def _result_fingerprint(self, plan: StudyPlan) -> str:
        """Fingerprint the scenario, compiled commands and every model input.

        A result is reusable only when this value and the complete artifact set
        match.  Output paths, console verbosity and cache location are excluded
        because they do not alter the numerical result or plots.
        """
        model_fingerprint = getattr(self, "_result_model_fingerprint", None)
        if model_fingerprint is None:
            model_digest = hashlib.sha256()
            model_digest.update(RESULT_ALGORITHM_VERSION.encode("ascii"))
            model_digest.update(
                _stable_json_bytes(
                    {
                        name: self.config.data.get(name, {})
                        for name in (
                            "psse",
                            "bases",
                            "system",
                            "load_flow",
                            "dynamics",
                            "initialization",
                            "channel_definition",
                            "playback",
                            "result_postprocessing",
                        )
                    }
                )
            )

            files = self.config.section("files")
            candidates = [
                ("sav", self.config.resolve(files["sav"])),
                ("dyr", self.config.resolve(files["dyr"])),
            ]
            for pattern in files.get("copy_globs", ["*.dll", "*.txt", "*.cfg"]):
                for path in sorted(self.config.base_dir.glob(pattern)):
                    candidates.append(("runtime:" + path.name, path))
            for name, value in sorted(self.config.section("definition_files").items()):
                candidates.append(
                    ("definition:" + str(name), self.config.resolve(str(value)))
                )
            hooks_file = self.config.data.get("hooks_file")
            if hooks_file:
                candidates.append(("hooks", self.config.resolve(str(hooks_file))))

            seen = set()
            for label, path in candidates:
                path = Path(path)
                identity = str(path.resolve())
                if identity in seen:
                    continue
                seen.add(identity)
                model_digest.update(str(label).encode("utf-8"))
                model_digest.update(path.name.encode("utf-8"))
                if path.is_file():
                    model_digest.update(_sha256_file(path).encode("ascii"))
                else:
                    model_digest.update(b"MISSING")
            model_fingerprint = model_digest.hexdigest()
            self._result_model_fingerprint = model_fingerprint

        digest = hashlib.sha256()
        digest.update(model_fingerprint.encode("ascii"))
        digest.update(
            _stable_json_bytes(
                {"scenario": plan.scenario.values, "plan": plan.as_dict()}
            )
        )
        return digest.hexdigest()

    @staticmethod
    def _write_result_metadata(
        json_path: Path,
        scenario_values,
        fingerprint: str,
        status: str,
        **metadata,
    ) -> None:
        payload = dict(scenario_values)
        payload[RESULT_METADATA_KEY] = {
            "schema_version": RESULT_METADATA_SCHEMA_VERSION,
            "algorithm_version": RESULT_ALGORITHM_VERSION,
            "fingerprint": fingerprint,
            "status": status,
            **metadata,
        }
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as stream:
            json.dump(
                payload,
                stream,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
                default=_json_default,
            )

    @staticmethod
    def _resume_result(
        json_path: Path,
        fingerprint: str,
        paths: dict,
    ) -> Optional[dict]:
        if not json_path.is_file():
            return None
        try:
            with open(json_path, "r", encoding="utf-8") as stream:
                payload = json.load(stream)
            metadata = payload.get(RESULT_METADATA_KEY, {})
        except (OSError, ValueError, TypeError):
            return None
        if (
            metadata.get("schema_version") != RESULT_METADATA_SCHEMA_VERSION
            or metadata.get("algorithm_version") != RESULT_ALGORITHM_VERSION
            or metadata.get("fingerprint") != fingerprint
            or metadata.get("status") != "completed"
        ):
            return None
        if any(
            not path.is_file() or path.stat().st_size <= 0
            for path in paths.values()
        ):
            return None
        result = {
            "status": "completed",
            "resume_status": "hit",
            "result_fingerprint": fingerprint,
            "elapsed_s": 0.0,
            "timings_s": {"resume_check": 0.0, "engine_total": 0.0},
        }
        result.update({name: str(path) for name, path in paths.items()})
        return result

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

            # Keep the filename presented to PSS/E short and conventional.
            # Python moves the successfully written SAV into the persistent
            # cache after PSS/E has closed it.
            temporary = cache.temporary_path(group, work_dir)
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
                reporter.emit(
                    prefix + " SAVE DISPATCHED SAV staging={} cache={}".format(
                        temporary.name, target
                    ),
                    "load",
                    "commands",
                )
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
        # Cache expensive SAV/DYR hashes across cases, but never across separate
        # run() calls where a model file may have changed in place.
        self._result_model_fingerprint = None
        output_root = self.config.resolve(self.config.data.get("output_dir", "outputs"))
        output_root.mkdir(parents=True, exist_ok=True)
        results: List[dict] = []
        continue_on_error = bool(self.config.data.get("continue_on_error", True))
        keep_runtime = bool(self.config.data.get("keep_runtime_files", False))
        keep_result_dyr = bool(self.config.data.get("keep_result_dyr", True))
        keep_initialised_sav = bool(self.config.data.get("keep_initialised_sav", True))
        keep_csv_results = bool(self.config.data.get("keep_csv_results", False))
        keep_scenario_json = bool(self.config.data.get("keep_scenario_json", True))
        resume_completed = bool(
            self.config.data.get("resume_completed_results", False)
        )
        resume_require_plots = bool(
            self.config.data.get("resume_require_plots", False)
        )
        in_memory_postprocessing = bool(
            self.config.data.get("in_memory_postprocessing", False)
        )
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
                result_dyr_path = result_dir / (plan.scenario.file_name + ".dyr")
                initialised_sav_path = result_dir / (
                    plan.scenario.file_name + "_initialised.sav"
                )
                initialised_staging_path = work_dir / (
                    "initialised_{}_{:04d}.sav".format(os.getpid(), number)
                )
                initialised_staging_path.unlink(missing_ok=True)
                assignment = dispatch_plan.assignments[number - 1] if dispatch_plan is not None else None
                dispatch_state = dispatch_states.get(assignment.key) if assignment is not None else None
                fingerprint = self._result_fingerprint(plan)
                expected_paths = {"json": json_path, "out": out_path}
                if keep_result_dyr:
                    expected_paths["dyr"] = result_dyr_path
                if keep_initialised_sav:
                    expected_paths["initialised_sav"] = initialised_sav_path
                if resume_require_plots:
                    expected_paths.update(
                        png=result_dir / (plan.scenario.file_name + ".png"),
                        pdf=result_dir / (plan.scenario.file_name + ".pdf"),
                    )
                resume_started = time.perf_counter()
                resumed = (
                    self._resume_result(json_path, fingerprint, expected_paths)
                    if resume_completed and keep_scenario_json
                    else None
                )
                if resumed is not None:
                    resumed["file_name"] = plan.scenario.file_name
                    resumed["timings_s"]["resume_check"] = round(
                        time.perf_counter() - resume_started, 6
                    )
                    if assignment is not None:
                        resumed["dispatch_key"] = assignment.short_key
                        resumed["dispatch_cache_status"] = (
                            dispatch_state.get("cache_status")
                            if dispatch_state
                            else "missing"
                        )
                    results.append(resumed)
                    reporter.emit(prefix + " RESUME HIT", "success", "cases")
                    if result_callback is not None:
                        result_callback(resumed, plan, number, total)
                    with open(output_root / "run_status.json", "w", encoding="utf-8") as stream:
                        json.dump(results, stream, indent=2, default=_json_default)
                    continue

                # The previous fingerprint is no longer reusable. Remove only
                # this case's exact artifacts before starting so a failed rerun
                # can never be mistaken for the older successful result.
                for stale_path in (
                    out_path,
                    csv_path,
                    result_dyr_path,
                    initialised_sav_path,
                    result_dir / (plan.scenario.file_name + ".png"),
                    result_dir / (plan.scenario.file_name + ".pdf"),
                    result_dir / (plan.scenario.file_name + "_FAILED.txt"),
                ):
                    stale_path.unlink(missing_ok=True)

                result = {
                    "file_name": plan.scenario.file_name,
                    "status": "running",
                    "resume_status": "miss" if resume_completed else "disabled",
                    "result_fingerprint": fingerprint,
                }
                if keep_scenario_json:
                    self._write_result_metadata(
                        json_path,
                        plan.scenario.values,
                        fingerprint,
                        "running",
                    )
                    result["json"] = str(json_path)
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
                timings = {}

                def record_timing(name, stage_started):
                    timings[name] = round(time.perf_counter() - stage_started, 6)

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

                    setup_started = time.perf_counter()
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
                    record_timing("case_setup", setup_started)

                    result_staging_started = time.perf_counter()
                    if keep_result_dyr:
                        _publish_by_link(dyr_path, result_dyr_path)
                        result["dyr"] = str(result_dyr_path)
                        reporter.emit(
                            prefix + " RESULT DYR " + str(result_dyr_path),
                            "load",
                            "commands",
                        )
                    record_timing("result_staging", result_staging_started)

                    dynamic_init_started = time.perf_counter()
                    reporter.emit(prefix + " DYNAMIC INIT " + str(dyr_path), "load", "commands")
                    playback_metadata = self.backend.initialize_dynamics(
                        work_dir,
                        dyr_path,
                        out_path,
                        plan.playback,
                        initialised_sav_path=(
                            initialised_staging_path if keep_initialised_sav else None
                        ),
                    )
                    record_timing("dynamic_initialization", dynamic_init_started)
                    if isinstance(playback_metadata, dict) and playback_metadata:
                        result["playback"] = {
                            key: value
                            for key, value in playback_metadata.items()
                            if key not in {"plb_path", "dyr_path"}
                        }
                        reporter.emit(
                            prefix
                            + " PLAYBACK {} points={} Vspan={:.6g} pu Fspan={:.6g} Hz".format(
                                playback_metadata.get("stem", "profile"),
                                playback_metadata.get("points", 0),
                                float(playback_metadata.get("voltage_span_pu", 0.0)),
                                float(playback_metadata.get("frequency_max_hz", 0.0))
                                - float(playback_metadata.get("frequency_min_hz", 0.0)),
                            ),
                            "load",
                            "commands",
                        )
                    if keep_initialised_sav:
                        initialised_publish_started = time.perf_counter()
                        if (
                            not initialised_staging_path.exists()
                            or initialised_staging_path.stat().st_size <= 0
                        ):
                            raise RuntimeError(
                                "PSS/E did not create initialised SAV {}".format(
                                    initialised_staging_path
                                )
                            )
                        _publish_by_move(
                            initialised_staging_path, initialised_sav_path
                        )
                        result["initialised_sav"] = str(initialised_sav_path)
                        reporter.emit(
                            prefix + " RESULT INITIALISED SAV " + str(initialised_sav_path),
                            "load",
                            "commands",
                        )
                        record_timing(
                            "initialised_sav_publish", initialised_publish_started
                        )
                    call_hook(self.hooks, "after_dynamic_initialization", self.backend, plan.scenario, work_dir)
                    simulation_started = time.perf_counter()
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
                    record_timing("simulation", simulation_started)
                    decode_started = time.perf_counter()
                    nominal_frequency = self.config.section("dynamics").get(
                        "frequency_hz", 50.0
                    )
                    if in_memory_postprocessing:
                        reporter.emit(
                            prefix + " DECODE OUT -> MEMORY", "load", "commands"
                        )
                        dataframe = out_to_dataframe(
                            str(out_path), self.dyntools, nominal_frequency
                        )
                        result["_dataframe"] = dataframe
                        if keep_csv_results or result_callback is None:
                            csv_started = time.perf_counter()
                            write_dataframe_csv(dataframe, str(csv_path))
                            result["csv"] = str(csv_path)
                            record_timing("csv_write", csv_started)
                    else:
                        reporter.emit(
                            prefix + " CONVERT OUT -> CSV", "load", "commands"
                        )
                        out_to_csv(
                            str(out_path),
                            str(csv_path),
                            self.dyntools,
                            nominal_frequency,
                        )
                        result["csv"] = str(csv_path)
                    record_timing("out_decode", decode_started)
                    result.update(
                        status="completed",
                        out=str(out_path),
                        elapsed_s=round(time.perf_counter() - started, 3),
                        timings_s=timings,
                    )
                    if json_path.exists():
                        result["json"] = str(json_path)
                except Exception as exc:
                    result.update(
                        status="failed",
                        error=str(exc),
                        traceback=traceback.format_exc(),
                        elapsed_s=round(time.perf_counter() - started, 3),
                        timings_s=timings,
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
                    initialised_staging_path.unlink(missing_ok=True)

                results.append(result)
                if result_callback is not None:
                    callback_started = time.perf_counter()
                    result_callback(result, plan, number, total)
                    timings["result_callback"] = round(
                        time.perf_counter() - callback_started, 6
                    )
                # DataFrames are an in-process hand-off only; never serialize
                # thousands of channel samples into run_status.json.
                result.pop("_dataframe", None)
                timings["engine_total"] = round(time.perf_counter() - started, 6)
                result["timings_s"] = timings
                if keep_scenario_json:
                    if result.get("status") != "completed":
                        metadata_status = "failed"
                    elif resume_require_plots and result.get("plot_status") not in {
                        "completed",
                        "reused",
                    }:
                        metadata_status = (
                            "failed"
                            if result.get("plot_status")
                            in {"failed", "skipped_invalid_tov"}
                            else "study_completed"
                        )
                    else:
                        metadata_status = "completed"
                    self._write_result_metadata(
                        json_path,
                        plan.scenario.values,
                        fingerprint,
                        metadata_status,
                        plot_status=result.get("plot_status"),
                        error=result.get("error") or result.get("plot_error"),
                    )
                with open(output_root / "run_status.json", "w", encoding="utf-8") as stream:
                    json.dump(results, stream, indent=2, default=_json_default)
                if stop_after_case:
                    break
        finally:
            self.backend.halt()
            if not keep_runtime:
                shutil.rmtree(str(work_dir), ignore_errors=True)
        return results
