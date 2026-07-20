from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config import ProjectConfig


class DefinitionError(ValueError):
    """Raised when the transparent Heywood definition files are incomplete."""


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        with open(str(path), "r", encoding="utf-8-sig") as stream:
            value = json.load(stream)
    except (OSError, ValueError) as exc:
        raise DefinitionError("Cannot read definition {}: {}".format(path, exc))
    if not isinstance(value, dict):
        raise DefinitionError("Definition {} must contain a JSON object".format(path))
    return value


def _one(directory: Path, pattern: str, required: bool = True) -> Optional[Path]:
    matches = sorted(directory.glob(pattern))
    if not matches:
        if required:
            raise DefinitionError("MODEL_DIR contains no {} file: {}".format(pattern, directory))
        return None
    if len(matches) > 1:
        names = ", ".join(item.name for item in matches)
        raise DefinitionError(
            "MODEL_DIR contains more than one {} file ({}). Select the files in open_psse_config.json.".format(
                pattern, names
            )
        )
    return matches[0]


def discover_model_files(model_dir: str, selections: Optional[Dict[str, Any]] = None) -> Dict[str, Path]:
    directory = Path(model_dir).resolve()
    if not directory.is_dir():
        raise DefinitionError("MODEL_DIR does not exist: {}".format(directory))
    selections = selections or {}
    configured_files = selections.get("files", {})
    configured_defs = selections.get("definition_files", {})

    def selected(name: str, pattern: str, configured: Dict[str, Any]) -> Path:
        value = configured.get(name)
        if value not in (None, ""):
            path = Path(str(value))
            path = path if path.is_absolute() else directory / path
            if not path.exists():
                raise DefinitionError("Configured {} file does not exist: {}".format(name, path))
            return path.resolve()
        return _one(directory, pattern)

    return {
        "sav": selected("sav", "*.sav", configured_files),
        "dyr": selected("dyr", "*.dyr", configured_files),
        "savdef": selected("savdef", "*.savdef", configured_defs),
        "initdef": selected("initdef", "*.initdef", configured_defs),
        "chandef": selected("chandef", "*.chandef", configured_defs),
    }


def _named(items: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(item["name"]): item for item in items}


def _branch(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "from_bus": int(item["from_bus"]),
        "to_bus": int(item["to_bus"]),
        "id": str(item.get("circuit_id", item.get("id", "1"))),
    }


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _model_lookup(model: Dict[str, Any]) -> Dict[str, Any]:
    model_type = str(model.get("model_type", "")).upper()
    if model_type == "OTHER_BUS":
        return {
            "method": "cctmind_buso",
            "bus": int(model["bus"]),
            "name": str(model["registered_name"]),
        }
    if model_type == "PLANT":
        return {
            "method": "mdlind",
            "bus": int(model["bus"]),
            "id": str(model.get("machine_id", model.get("mach_id", "1"))),
            "class": str(model.get("slot", "GEN")),
        }
    raise DefinitionError("Unsupported savdef model_type {!r}".format(model_type))


def build_project_data(model_dir: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Translate Pallet's JSON schemas into an explicit native-psspy config.

    The schemas remain the source of truth. No proprietary Pallet classes are
    imported and no case-specific bus numbers are hidden in Python code.
    """
    paths = discover_model_files(model_dir, overrides)
    savdef = _load_json(paths["savdef"])
    initdef = _load_json(paths["initdef"])
    chandef = _load_json(paths["chandef"])

    buses = _named(savdef.get("buses", []))
    branches_source = _named(savdef.get("branches", []))
    branches = {name: _branch(item) for name, item in branches_source.items()}
    machines = _named(savdef.get("machines", []))
    transformers = {
        str(item["name"]): {
            "from_bus": int(item["from_bus"]),
            "to_bus": int(item["to_bus"]),
            "id": str(item.get("id", "1")),
        }
        for item in savdef.get("two_windings", [])
    }

    grid_name = str(initdef.get("grid_branch_name") or initdef.get("grid_impedance_setter", {}).get("grid_branch_name") or "grid")
    if grid_name not in branches:
        raise DefinitionError("initdef grid branch {!r} is absent from savdef".format(grid_name))
    grid_branch = branches[grid_name]

    playback_machine = savdef.get("playback_machine") or {}
    infinite_bus = int(playback_machine["bus"])
    infinite_machine_id = str(playback_machine.get("mach_id", "1"))

    vpoc = initdef.get("vpoc_controller") or {}
    poc_name = str((vpoc.get("poc_bus") or {}).get("name", "POC"))
    if poc_name not in buses:
        raise DefinitionError("initdef POC bus {!r} is absent from savdef".format(poc_name))
    poc_bus = int(buses[poc_name]["num"])

    fixed_shunts = {
        str(item.get("name", "shunt")): {
            "bus": int(item["bus"]), "id": str(item.get("id", "1"))
        }
        for item in savdef.get("fixed_shunts", [])
    }
    loads = {
        str(item["name"]): {"bus": int(item["bus"]), "id": str(item.get("id", "1"))}
        for item in savdef.get("loads", [])
    }
    fault_bus = int(fixed_shunts.get("tov", {}).get("bus", buses.get("888888", {}).get("num", poc_bus)))

    bus_aliases: Dict[str, int] = {}
    for name, item in buses.items():
        bus_aliases[name] = int(item["num"])
        bus_aliases[name.lower()] = int(item["num"])
    bus_aliases.update({
        "poc": poc_bus,
        "fault": fault_bus,
        # Alias used by the supplied HY SPEC fault command language.
        "3HYWDBS_275E": fault_bus,
    })

    p_controllers = initdef.get("iterative_p_controllers") or []
    p_machine_settings: Dict[str, Dict[str, Any]] = {}
    for controller in p_controllers:
        for item in controller.get("machines", []):
            p_machine_settings[str(item["name"])] = item
    q_settings = {
        str(item["name"]): item
        for item in (initdef.get("var_rebalancer") or {}).get("enrolled_machines", [])
    }
    enrolled = [str(item["name"]) for item in vpoc.get("enrolled_machines", [])]
    if not enrolled:
        enrolled = list(p_machine_settings)
    generators: List[Dict[str, Any]] = []
    for name in enrolled:
        if name not in machines:
            raise DefinitionError("initdef machine {!r} is absent from savdef".format(name))
        source = machines[name]
        p_item, q_item = p_machine_settings.get(name, {}), q_settings.get(name, {})
        generators.append({
            "name": name,
            "bus": int(source["bus"]),
            "id": str(source.get("mach_id", "1")),
            "p_weight": float(p_item.get("scaling", 1.0 / max(1, len(enrolled)))),
            "pmin_mw": float(p_item.get("pmin_mw", -9999.0)),
            "pmax_mw": float(p_item.get("pmax_mw", 9999.0)),
            "q_weight": float(q_item.get("weighting", 1.0 / max(1, len(enrolled)))),
            "qmin_mvar": float(q_item.get("qmin_mvar", -9999.0)),
            "qmax_mvar": float(q_item.get("qmax_mvar", 9999.0)),
        })

    model_lookups = {
        str(item["name"]): _model_lookup(item) for item in savdef.get("models", [])
    }
    q_controllers = initdef.get("qbranch_via_vsched_controllers") or []
    q_tolerance = 0.1
    measurement_branch = branches.get("meter", grid_branch)
    if q_controllers:
        q_controller = q_controllers[0]
        q_tolerance = float(q_controller.get("convergence_tolerance_mvar", q_tolerance))
        measurement = (q_controller.get("measurement_branches") or [{}])[0]
        measurement_branch = branches.get(str(measurement.get("name", "meter")), measurement_branch)
    p_tolerance = 0.1
    p_max_iterations = 40
    p_acceleration = 1.0
    if p_controllers:
        p_tolerance = float(p_controllers[0].get("convergence_tolerance_mw", p_tolerance))
        p_max_iterations = int(p_controllers[0].get("max_iterations", p_max_iterations))
        p_acceleration = float(p_controllers[0].get("acceleration_factor", p_acceleration))

    data: Dict[str, Any] = {
        "project_root": str(Path(model_dir).resolve()),
        "continue_on_error": True,
        "psse": {"version": 34, "max_buses": 200000},
        "files": {
            "sav": paths["sav"].name,
            "dyr": paths["dyr"].name,
            "copy_globs": ["*.dll", "*.txt", "*.cfg", "*.plb"],
        },
        "definition_files": {
            "savdef": paths["savdef"].name,
            "initdef": paths["initdef"].name,
            "chandef": paths["chandef"].name,
        },
        "bases": {
            "p_mw": 285.0,
            "q_mvar": 112.575,
            "s_mva": 306.42801866833264,
            "normal_v_pu": 1.06,
            "frequency_hz": 50.0,
        },
        "system": {
            "poc_bus": poc_bus,
            "infinite_bus": infinite_bus,
            "fault_bus": fault_bus,
            "bus_aliases": bus_aliases,
            "grid_branch": grid_branch,
            "measurement_branch": measurement_branch,
            "branches": branches,
            "infinite_machine": {"bus": infinite_bus, "id": infinite_machine_id},
            "generators": generators,
            "fixed_shunts": fixed_shunts,
            "loads": loads,
        },
        "models": model_lookups,
        "transformers": transformers,
        "initialization": initdef,
        "channel_definition": chandef,
        "load_flow": {
            "solve_repetitions": 2,
            "max_iterations": max(int(initdef.get("max_initialiser_iterations", 400)), p_max_iterations),
            "tolerance_mw_mvar": min(p_tolerance, q_tolerance),
            "p_tolerance_mw": p_tolerance,
            "q_tolerance_mvar": q_tolerance,
            "correction_gain": 1.0,
            "acceleration_factor": p_acceleration,
        },
        "dynamics": {
            "frequency_hz": 50.0,
            "frequency_dependence": False,
            "iterations": 1000,
            "acceleration": 0.1,
            "tolerance": 0.0005,
            "frequency_filter_s": 0.016,
            "time_step_s": 0.001,
            "nprt": 5000,
            "nplt": 0,
        },
        "playback": {"file_stem": "playback"},
    }
    return _deep_merge(data, overrides or {})


def load_or_build_project_config(model_dir: str) -> ProjectConfig:
    """Load optional overrides, otherwise build directly from the three defs."""
    directory = Path(model_dir).resolve()
    config_path = directory / "open_psse_config.json"
    overrides: Dict[str, Any] = {}
    if config_path.exists():
        with open(str(config_path), "r", encoding="utf-8-sig") as stream:
            overrides = json.load(stream)
        if not isinstance(overrides, dict):
            raise DefinitionError("{} must contain a JSON object".format(config_path))
    data = build_project_data(str(directory), overrides)
    # The generated config is deliberately kept in memory; a user override file
    # remains optional and contains only values that genuinely differ.
    config = ProjectConfig(str(config_path), data)
    config.validate()
    return config
