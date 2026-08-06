from __future__ import annotations

import datetime as _datetime
import hashlib
import json
import math
import os
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .models import Scenario, StudyPlan
from .profiles import initial_signal_value


DISPATCH_CACHE_SCHEMA_VERSION = 1
DISPATCH_ALGORITHM_VERSION = "native-grid-pqv-v1"

CORE_SIGNATURE_NAMES = {
    "is_infinite",
    "fault_level_mva",
    "grid_x_over_r",
    "p_target_mw",
    "q_target_mvar",
    "vpoc_pu",
}

CORE_SOURCE_COLUMNS = {
    "Is_Infinite",
    "Grid_FL_MVA_sig",
    "Grid_SCR",
    "Grid_X2R_sig",
    "Pbase_MW",
    "Ppoc_MW_sig",
    "Ppoc_pu",
    "Qpoc_MVAr_init",
    "Qpoc_pu",
    "Vpoc_pu_sig",
}

AUTO_COLUMN_PATTERNS = (
    re.compile(r"(?:^|[_ -])(?:number|num|no|n)(?:[_ -]*of)?[_ -]*(?:inverters?|inv)(?:$|[_ -])", re.I),
    re.compile(r"(?:inverters?|inv).*(?:in[_ -]*service|online|available|count|status|enabled)", re.I),
    re.compile(r"(?:^|[_ -])(?:temperature|temp)(?:$|[_ -])", re.I),
    re.compile(r"(?:control|operating)[_ -]*mode", re.I),
    re.compile(r"(?:^|[_ -])(?:p|q|pf|var|voltage|frequency)[_ -]*mode(?:$|[_ -])", re.I),
    re.compile(r"(?:^|[_ -])(?:unit|plant)[_ -]*status(?:$|[_ -])", re.I),
    re.compile(r"(?:^|[_ -])tap(?:[_ -]*(?:enable|ratio|position|mode))?(?:$|[_ -])", re.I),
    re.compile(r"(?:^|[_ -])initial(?:[_ -]|$)|(?:_init|_initial)$", re.I),
)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value == ""
    if type(value).__name__ in {"NAType", "NaTType"}:
        return True
    try:
        return bool(value != value)
    except Exception:
        return False


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not _is_missing(value):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_float(value: Any, name: str) -> float:
    if _is_missing(value):
        raise ValueError("Missing dispatch input {}".format(name))
    try:
        result = initial_signal_value(value)
    except (TypeError, ValueError):
        raise ValueError("Dispatch input {} must be numeric; got {!r}".format(name, value))
    if not math.isfinite(result):
        raise ValueError("Dispatch input {} must be finite; got {!r}".format(name, value))
    return result


def _stable_float(value: Any, name: str) -> float:
    result = _as_float(value, name)
    if result == 0.0:
        return 0.0
    return float(format(result, ".12g"))


def canonical_value(value: Any) -> Any:
    """Convert spreadsheet/numpy values into stable JSON cache-key values."""
    item = getattr(value, "item", None)
    if callable(item):
        try:
            value = item()
        except Exception:
            pass
    if _is_missing(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return _stable_float(value, "extra dispatch key value")
    if isinstance(value, dict):
        return {str(key): canonical_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [canonical_value(item) for item in value]
    return str(value).strip()


def resolve_dispatch_inputs(scenario: Scenario, config) -> Dict[str, Any]:
    """Resolve exactly the steady-state inputs used by the native backend."""
    bases = config.section("bases")
    plant_p_base = _as_float(bases.get("p_mw"), "plant P base")
    grid_p_base = _as_float(scenario.get("Pbase_MW", plant_p_base), "grid P base")
    q_base = _as_float(bases.get("q_mvar", plant_p_base), "Q base")

    fault_level = scenario.get("Grid_FL_MVA_sig")
    if _is_missing(fault_level):
        scr = scenario.get("Grid_SCR")
        if _is_missing(scr):
            raise ValueError("Scenario has neither Grid_FL_MVA_sig nor Grid_SCR")
        fault_level = _as_float(scr, "Grid_SCR") * grid_p_base

    p_target = scenario.get("Ppoc_MW_sig")
    if _is_missing(p_target):
        p_target = _as_float(scenario.get("Ppoc_pu", 0.0), "Ppoc_pu") * plant_p_base

    q_target = scenario.get("Qpoc_MVAr_init")
    if _is_missing(q_target):
        q_target = _as_float(scenario.get("Qpoc_pu", 0.0), "Qpoc_pu") * q_base

    return {
        "is_infinite": _as_bool(scenario.get("Is_Infinite", False)),
        "fault_level_mva": _as_float(fault_level, "Grid_FL_MVA_sig"),
        "grid_x_over_r": _as_float(scenario.get("Grid_X2R_sig"), "Grid_X2R_sig"),
        "p_target_mw": _as_float(p_target, "Ppoc_MW_sig"),
        "q_target_mvar": _as_float(q_target, "Qpoc_MVAr_init"),
        "vpoc_pu": _as_float(
            scenario.get("Vpoc_pu_sig", bases.get("normal_v_pu", 1.0)), "Vpoc_pu_sig"
        ),
    }


def infer_dispatch_key_columns(
    scenarios: Iterable[Scenario],
    explicit_columns: Optional[Sequence[str]] = None,
    automatic: bool = True,
) -> List[str]:
    """Add likely initial unit-count, temperature and control-mode columns."""
    selected: List[str] = []
    seen = set()
    for column in explicit_columns or []:
        name = str(column)
        if name not in seen:
            selected.append(name)
            seen.add(name)
    if not automatic:
        return selected
    all_columns = []
    for scenario in scenarios:
        for column in scenario.values:
            name = str(column)
            if name not in all_columns:
                all_columns.append(name)
    for name in all_columns:
        if name in seen or name in CORE_SOURCE_COLUMNS:
            continue
        if any(pattern.search(name) for pattern in AUTO_COLUMN_PATTERNS):
            selected.append(name)
            seen.add(name)
    return selected


def build_dispatch_signature(
    scenario: Scenario,
    config,
    extra_columns: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    resolved = resolve_dispatch_inputs(scenario, config)
    signature = {
        name: (value if isinstance(value, bool) else _stable_float(value, name))
        for name, value in resolved.items()
    }
    extras = {
        str(column): canonical_value(scenario.values.get(str(column)))
        for column in (extra_columns or [])
    }
    if extras:
        signature["extra"] = extras
    return signature


def dispatch_key(signature: Dict[str, Any]) -> str:
    encoded = json.dumps(signature, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass
class DispatchAssignment:
    key: str
    short_key: str
    signature: Dict[str, Any]


@dataclass
class DispatchGroup:
    key: str
    short_key: str
    signature: Dict[str, Any]
    plans: List[StudyPlan] = field(default_factory=list)

    @property
    def representative(self) -> StudyPlan:
        return self.plans[0]


@dataclass
class DispatchPlan:
    assignments: List[DispatchAssignment]
    groups: List[DispatchGroup]
    extra_columns: List[str]


def create_dispatch_plan(
    plans: Sequence[StudyPlan],
    config,
    explicit_columns: Optional[Sequence[str]] = None,
    automatic_columns: bool = True,
) -> DispatchPlan:
    scenarios = [plan.scenario for plan in plans]
    extra_columns = infer_dispatch_key_columns(scenarios, explicit_columns, automatic_columns)
    grouped: "OrderedDict[str, DispatchGroup]" = OrderedDict()
    assignments: List[DispatchAssignment] = []
    for plan in plans:
        signature = build_dispatch_signature(plan.scenario, config, extra_columns)
        key = dispatch_key(signature)
        assignment = DispatchAssignment(key=key, short_key=key[:16], signature=signature)
        assignments.append(assignment)
        if key not in grouped:
            grouped[key] = DispatchGroup(key=key, short_key=key[:16], signature=signature)
        grouped[key].plans.append(plan)
    return DispatchPlan(assignments=assignments, groups=list(grouped.values()), extra_columns=extra_columns)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _stable_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")


def dispatch_model_fingerprint(config) -> str:
    """Fingerprint every static input that can change a dispatched SAV."""
    digest = hashlib.sha256()
    digest.update(DISPATCH_ALGORITHM_VERSION.encode("ascii"))
    files = config.section("files")
    candidates = [("sav", config.resolve(files["sav"]))]
    for name, value in sorted(config.section("definition_files").items()):
        candidates.append(("definition:" + str(name), config.resolve(str(value))))
    hooks_file = config.data.get("hooks_file")
    if hooks_file:
        candidates.append(("hooks", config.resolve(str(hooks_file))))
    for label, path in candidates:
        path = Path(path)
        digest.update(label.encode("utf-8"))
        digest.update(str(path.name).encode("utf-8"))
        if path.exists() and path.is_file():
            digest.update(_sha256_file(path).encode("ascii"))
        else:
            digest.update(b"MISSING")
    dispatch_config = {
        "psse": config.section("psse"),
        "bases": config.section("bases"),
        "system": config.section("system"),
        "load_flow": config.section("load_flow"),
        "initialization": config.section("initialization"),
    }
    digest.update(_stable_json_bytes(dispatch_config))
    return digest.hexdigest()


def _utc_now() -> str:
    return _datetime.datetime.now(_datetime.timezone.utc).replace(microsecond=0).isoformat()


class DispatchCache:
    """Persistent, model-fingerprinted store of solved dispatched SAV cases."""

    def __init__(self, config, root: Path, rebuild: bool = False, verify_hashes: bool = False):
        self.config = config
        self.root = Path(root).resolve()
        self.rebuild = bool(rebuild)
        self.verify_hashes = bool(verify_hashes)
        self.model_fingerprint = dispatch_model_fingerprint(config)
        self.directory = self.root / ("model_" + self.model_fingerprint[:16])
        self.directory.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.directory / "dispatch_manifest.json"
        self.manifest = self._load_manifest()

    def _new_manifest(self) -> Dict[str, Any]:
        return {
            "schema_version": DISPATCH_CACHE_SCHEMA_VERSION,
            "algorithm_version": DISPATCH_ALGORITHM_VERSION,
            "model_fingerprint": self.model_fingerprint,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "cases": {},
        }

    def _load_manifest(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            return self._new_manifest()
        try:
            with open(str(self.manifest_path), "r", encoding="utf-8") as stream:
                value = json.load(stream)
        except Exception:
            return self._new_manifest()
        if (
            value.get("schema_version") != DISPATCH_CACHE_SCHEMA_VERSION
            or value.get("algorithm_version") != DISPATCH_ALGORITHM_VERSION
            or value.get("model_fingerprint") != self.model_fingerprint
            or not isinstance(value.get("cases"), dict)
        ):
            return self._new_manifest()
        return value

    def _record_path(self, record: Dict[str, Any]) -> Optional[Path]:
        name = record.get("sav_file")
        if not name:
            return None
        path = (self.directory / str(name)).resolve()
        if path.parent != self.directory.resolve():
            return None
        return path

    def cached_path(self, group: DispatchGroup) -> Optional[Path]:
        if self.rebuild:
            return None
        record = self.manifest["cases"].get(group.key)
        if not isinstance(record, dict) or record.get("status") != "completed":
            return None
        if record.get("signature") != group.signature:
            return None
        path = self._record_path(record)
        if path is None or not path.exists() or path.stat().st_size <= 0:
            return None
        if self.verify_hashes and record.get("sha256") != _sha256_file(path):
            return None
        return path

    def target_path(self, group: DispatchGroup) -> Path:
        return self.directory / ("dispatch_" + group.short_key + ".sav")

    def temporary_path(self, group: DispatchGroup) -> Path:
        return self.directory / (".dispatch_{}_{}.tmp.sav".format(group.short_key, os.getpid()))

    def publish(self, temporary_path: Path, target_path: Path) -> None:
        if not temporary_path.exists() or temporary_path.stat().st_size <= 0:
            raise RuntimeError("PSS/E did not create dispatched SAV {}".format(temporary_path))
        os.replace(str(temporary_path), str(target_path))

    def record_success(self, group: DispatchGroup, path: Path) -> None:
        self.manifest["cases"][group.key] = {
            "status": "completed",
            "short_key": group.short_key,
            "signature": group.signature,
            "sav_file": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
            "representative_file": group.representative.scenario.file_name,
            "created_at": _utc_now(),
        }
        self._write_manifest()

    def record_failure(self, group: DispatchGroup, error: str) -> None:
        self.manifest["cases"][group.key] = {
            "status": "failed",
            "short_key": group.short_key,
            "signature": group.signature,
            "representative_file": group.representative.scenario.file_name,
            "error": str(error),
            "attempted_at": _utc_now(),
        }
        self._write_manifest()

    def _write_manifest(self) -> None:
        self.manifest["updated_at"] = _utc_now()
        temporary = self.manifest_path.with_name(
            ".{}_{}.tmp".format(self.manifest_path.name, os.getpid())
        )
        with open(str(temporary), "w", encoding="utf-8") as stream:
            json.dump(self.manifest, stream, indent=2, sort_keys=True, ensure_ascii=False)
        os.replace(str(temporary), str(self.manifest_path))
