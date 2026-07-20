from __future__ import annotations

import json
import os
import shutil
import tempfile
import traceback
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from .backend import PsseBackend
from .bootstrap import import_psse
from .commands import build_plan
from .hooks import call_hook, load_hooks
from .models import Scenario, StudyPlan
from .output import out_to_csv


def _json_default(value):
    """Convert pandas/numpy scalar values without importing those packages."""
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
        if keep_runtime:
            work_dir = output_root / "_runtime"
            work_dir.mkdir(parents=True, exist_ok=True)
        else:
            work_dir = Path(tempfile.mkdtemp(prefix="hbess_psse_"))

        try:
            sav_path, dyr_path = self._copy_inputs(work_dir)
            total = len(plans)
            for number, plan in enumerate(plans, start=1):
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
                result = {"file_name": plan.scenario.file_name, "status": "running"}
                if keep_runtime:
                    result["work_dir"] = str(work_dir)
                previous_cwd = Path.cwd()
                stop_after_case = False
                try:
                    os.chdir(str(work_dir))
                    call_hook(self.hooks, "before_case", self.backend, plan.scenario, work_dir)
                    self.backend.initialize(sav_path, work_dir / plan.scenario.file_name)
                    self.backend.configure_scenario_options(plan.scenario)
                    r_pu, x_pu = self.backend.configure_grid(plan.scenario)
                    self.backend.dispatch(plan.scenario, r_pu, x_pu)
                    if bool(plan.scenario.get("Is_Infinite", False)):
                        self.backend.make_grid_infinite()
                    call_hook(self.hooks, "after_dispatch", self.backend, plan.scenario, work_dir)
                    self.backend.initialize_dynamics(work_dir, dyr_path, out_path, plan.playback)
                    call_hook(self.hooks, "after_dynamic_initialization", self.backend, plan.scenario, work_dir)
                    current_time = 0.0
                    for event in plan.events:
                        if event.time < current_time:
                            raise RuntimeError("Events are not time ordered")
                        if event.time > current_time:
                            self.backend.run_to(event.time)
                            current_time = event.time
                        self.backend.apply_event(event, plan.scenario)
                    if plan.scenario.end_time > current_time:
                        self.backend.run_to(plan.scenario.end_time)
                    out_to_csv(
                        str(out_path), str(csv_path), self.dyntools,
                        self.config.section("dynamics").get("frequency_hz", 50.0),
                    )
                    result.update(status="completed", out=str(out_path), csv=str(csv_path))
                    if json_path.exists():
                        result["json"] = str(json_path)
                except Exception as exc:
                    result.update(status="failed", error=str(exc), traceback=traceback.format_exc())
                    failure_path = result_dir / (plan.scenario.file_name + "_FAILED.txt")
                    with open(failure_path, "w", encoding="utf-8") as stream:
                        stream.write(result["traceback"])
                    result["failure_log"] = str(failure_path)
                    stop_after_case = not continue_on_error
                finally:
                    self.backend.halt()
                    os.chdir(str(previous_cwd))

                results.append(result)
                if result_callback is not None:
                    result_callback(result, plan, number, total)
                with open(output_root / "run_status.json", "w", encoding="utf-8") as stream:
                    json.dump(results, stream, indent=2)
                if stop_after_case:
                    break
        finally:
            self.backend.halt()
            if not keep_runtime:
                shutil.rmtree(str(work_dir), ignore_errors=True)
        return results
