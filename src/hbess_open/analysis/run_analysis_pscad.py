"""Declarative PSCAD clause-analysis orchestration.

This module intentionally contains no PSCAD simulation control.  It discovers
completed result files, groups them by sidecar metadata when requested, and
dispatches them to transparent clause functions in ``clause_analysis``.
"""

from __future__ import annotations

import json
import inspect
import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from hbess_open.analysis.clause_analysis.cumulative_rt_characteristics import produce_cumulative_ride_through_outputs
from hbess_open.analysis.clause_analysis.s52511_dpdf_analysis import produce_s52511_dpdf_outputs
from hbess_open.analysis.clause_analysis.s52513_disturbance_analysis import produce_disturbance_analysis_outputs
from hbess_open.analysis.clause_analysis.s52513_ort_analysis import produce_ort_plots
from hbess_open.analysis.clause_analysis.s52513_vdroop_analysis import produce_vdroop_outputs
from hbess_open.analysis.clause_analysis.s5254_cuo_analysis import produce_cuo_summary_outputs
from hbess_open.analysis.clause_analysis.s5255_iq_analysis import produce_s5255_iq_outputs
from hbess_open.analysis.clause_analysis.s5255_mfrt_analysis import produce_s5255_mfrt_outputs
from hbess_open.analysis.clause_analysis.s5255_phase_health_analysis import conduct_phase_voltage_analysis
from hbess_open.analysis.clause_analysis.s5255_rise_settle_recovery_analysis import produce_s5255_rise_settle_recovery_curve
from hbess_open.analysis.clause_analysis.s5258_disturbance_analysis import p_reduction_table
from hbess_open.analysis.clause_analysis.s5258_protection_trip_analysis import calculate_s5258_protection_trip_time
from hbess_open.analysis.clause_analysis.s528_max_fault_current_analysis import produce_s528_max_fault_current_outputs
from hbess_open.io.result_data import load_case_spec, spec_value


def _protection_trip_handler(psout_paths, **options):
    options.setdefault("x86", False)
    return calculate_s5258_protection_trip_time(out_paths=psout_paths, **options)


PSCAD_CLAUSE_HANDLERS = {
    "cumulative_ride_through": produce_cumulative_ride_through_outputs,
    "s52511_dpdf": produce_s52511_dpdf_outputs,
    "s52513_disturbance": produce_disturbance_analysis_outputs,
    "s52513_ort": produce_ort_plots,
    "s52513_vdroop": produce_vdroop_outputs,
    "s5254_cuo": produce_cuo_summary_outputs,
    "s5255_iq": produce_s5255_iq_outputs,
    "s5255_mfrt": produce_s5255_mfrt_outputs,
    "s5255_phase_health": conduct_phase_voltage_analysis,
    "s5255_rise_settle_recovery": produce_s5255_rise_settle_recovery_curve,
    "s5258_active_power_reduction": p_reduction_table,
    "s5258_protection_trip": _protection_trip_handler,
    "s528_max_fault_current": produce_s528_max_fault_current_outputs,
}


@dataclass(frozen=True)
class ResultSelector:
    root: str
    pattern: str = "**/*"
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()

    @classmethod
    def from_value(cls, value) -> "ResultSelector":
        if isinstance(value, str):
            return cls(root=value)
        return cls(
            root=str(value["root"]),
            pattern=str(value.get("pattern") or "**/*"),
            include=tuple(str(item) for item in value.get("include") or ()),
            exclude=tuple(str(item) for item in value.get("exclude") or ()),
        )


@dataclass(frozen=True)
class PscadAnalysisJob:
    name: str
    handler: str
    inputs: tuple[ResultSelector, ...]
    options: Mapping[str, Any] = field(default_factory=dict)
    group_by: tuple[str, ...] = ()
    sort_by: Optional[str] = None
    enabled: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PscadAnalysisJob":
        inputs = tuple(ResultSelector.from_value(item) for item in value.get("inputs") or ())
        if not inputs:
            raise ValueError("PSCAD analysis job {!r} has no input selectors".format(value.get("name")))
        return cls(
            name=str(value["name"]),
            handler=str(value["handler"]),
            inputs=inputs,
            options=dict(value.get("options") or {}),
            group_by=tuple(str(item) for item in value.get("group_by") or ()),
            sort_by=str(value["sort_by"]) if value.get("sort_by") else None,
            enabled=bool(value.get("enabled", True)),
        )


def list_pscad_clause_handlers() -> tuple[str, ...]:
    return tuple(sorted(PSCAD_CLAUSE_HANDLERS))


def _matches(path: Path, patterns: Sequence[str]) -> bool:
    text = path.as_posix()
    return any(fnmatchcase(path.name, pattern) or fnmatchcase(path.stem, pattern) or fnmatchcase(text, pattern) for pattern in patterns)


def _collect_paths(
    job: PscadAnalysisJob,
    roots: Mapping[str, str],
    extension: str,
    strict_inputs: bool,
) -> list[str]:
    paths: list[Path] = []
    suffix = extension.lower()
    for selector in job.inputs:
        if selector.root not in roots:
            raise KeyError("PSCAD analysis root {!r} is not configured".format(selector.root))
        root = Path(roots[selector.root])
        if not root.is_dir():
            if strict_inputs:
                raise FileNotFoundError("PSCAD analysis root does not exist: {}".format(root))
            continue
        for path in root.glob(selector.pattern):
            if not path.is_file() or path.suffix.lower() != suffix:
                continue
            if selector.include and not _matches(path, selector.include):
                continue
            if selector.exclude and _matches(path, selector.exclude):
                continue
            paths.append(path)
    return [str(path) for path in sorted(set(paths), key=lambda item: str(item).casefold())]


def _safe_group_name(values: Sequence[Any]) -> str:
    text = "_".join(str(value) for value in values)
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_.")
    return text or "group"


def _group_paths(job: PscadAnalysisJob, paths: Sequence[str]):
    if not job.group_by:
        ordered = list(paths)
        if job.sort_by:
            ordered.sort(key=lambda path: spec_value(load_case_spec(path), job.sort_by))
        return [("all", ordered)]

    groups: dict[tuple, list[str]] = {}
    for path in paths:
        spec = load_case_spec(path)
        key = tuple(spec_value(spec, name) for name in job.group_by)
        groups.setdefault(key, []).append(path)
    output = []
    for key, grouped_paths in groups.items():
        if job.sort_by:
            grouped_paths.sort(key=lambda path: spec_value(load_case_spec(path), job.sort_by))
        output.append((_safe_group_name(key), grouped_paths))
    return sorted(output, key=lambda item: item[0].casefold())


_OUTPUT_OPTION_NAMES = {"output_path", "output_png_path", "output_csv_path", "output_dir"}


def _job_options(job: PscadAnalysisJob, output_root: Path, group_name: str) -> dict:
    options = dict(job.options)
    for key in _OUTPUT_OPTION_NAMES.intersection(options):
        value = str(options[key]).format(job=_safe_group_name((job.name,)), group=group_name)
        path = Path(value)
        if not path.is_absolute():
            path = output_root / path
        options[key] = str(path)
    return options


def _resolve_handler(name: str, registry: Mapping[str, Callable]) -> Callable:
    try:
        return registry[name]
    except KeyError as exc:
        hint = get_close_matches(name, list(registry), n=3, cutoff=0.45)
        message = "Unknown PSCAD clause handler {!r}".format(name)
        if hint:
            message += "; closest: {}".format(", ".join(hint))
        raise KeyError(message) from exc


def run_analysis_pscad(
    ANALYSIS_TO_RUN: Sequence[str],
    ANALYSIS_JOBS: Sequence[Mapping[str, Any]],
    INPUT_DIRS: Mapping[str, str],
    OUTPUTS_DIR: str,
    extension: str = ".psout",
    continue_on_error: bool = True,
    strict_inputs: bool = True,
    status_path: Optional[str] = None,
    registry: Optional[Mapping[str, Callable]] = None,
):
    """Run selected, declaratively configured PSCAD post-processing jobs.

    Project-specific paths, signal names and characteristic points live in the
    outer master as job data; all discovery and dispatch logic remains here in
    ``src``.
    """
    extension = extension.lower()
    if extension not in {".psout", ".pkl", ".pickle", ".csv"}:
        raise ValueError("Unsupported PSCAD analysis extension: {}".format(extension))

    jobs = [PscadAnalysisJob.from_mapping(item) for item in ANALYSIS_JOBS]
    by_name: dict[str, PscadAnalysisJob] = {}
    for job in jobs:
        if job.name in by_name:
            raise ValueError("Duplicate PSCAD analysis job name: {}".format(job.name))
        by_name[job.name] = job

    selected = [str(name) for name in ANALYSIS_TO_RUN]
    missing = [name for name in selected if name not in by_name]
    if missing:
        raise ValueError("Selected PSCAD analyses have no job definition: {}".format(", ".join(missing)))
    if not selected:
        print("No PSCAD clause analyses selected.")
        return []

    handlers = dict(PSCAD_CLAUSE_HANDLERS)
    if registry:
        handlers.update(registry)
    output_root = Path(OUTPUTS_DIR)
    output_root.mkdir(parents=True, exist_ok=True)
    status = []

    for name in selected:
        job = by_name[name]
        if not job.enabled:
            status.append({"name": name, "status": "skipped", "reason": "job disabled"})
            continue
        try:
            paths = _collect_paths(job, INPUT_DIRS, extension, strict_inputs)
            if not paths:
                raise FileNotFoundError("No {} files matched PSCAD analysis job {!r}".format(extension, name))
            groups = _group_paths(job, paths)
            if len(groups) > 1:
                output_templates = [str(job.options[key]) for key in _OUTPUT_OPTION_NAMES.intersection(job.options)]
                if not any("{group}" in value for value in output_templates):
                    raise ValueError("Grouped job {!r} needs {{group}} in an output path".format(name))
            handler = _resolve_handler(job.handler, handlers)
            for group_name, group_paths in groups:
                options = _job_options(job, output_root, group_name)
                if "x86" in inspect.signature(handler).parameters:
                    options.setdefault("x86", False)
                handler(psout_paths=group_paths, **options)
            status.append({"name": name, "status": "completed", "files": len(paths), "groups": len(groups)})
            print("ANALYSIS OK: {} ({} files)".format(name, len(paths)))
        except Exception as exc:
            status.append({"name": name, "status": "failed", "error": str(exc)})
            print("ANALYSIS FAILED: {}: {}".format(name, exc))
            if not continue_on_error:
                raise

    if status_path:
        target = Path(status_path)
        if not target.is_absolute():
            target = output_root / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status
