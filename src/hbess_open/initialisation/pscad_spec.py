"""PSCAD SPEC initialisation with deterministic Vslack/TOV caching."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

import pandas as pd

from hbess_open.io.signal_dsl import ParsedSignal

from .grid_equivalent import (
    calculate_tov_shunt_mvar,
    calculate_vslack_pu,
    shunt_mvar_to_capacitance_uf,
)


_FALSE_VALUES = {"", "0", "false", "f", "no", "n", "off", "nan", "none"}
_TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}
_KEY_COLUMNS = (
    "Grid_FL_MVA_sig",
    "Grid_X2R_sig",
    "Vpoc_pu_sig",
    "Ppoc_MW",
    "Qpoc_MVAr",
    "U_Ov",
)
def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _as_bool(value: Any) -> bool:
    if _is_blank(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in _FALSE_VALUES:
        return False
    if text in _TRUE_VALUES:
        return True
    return bool(text)


def _initial_numeric(value: Any, label: str) -> float:
    if _is_blank(value):
        raise ValueError("{} is blank".format(label))
    if isinstance(value, str):
        parsed = ParsedSignal.parse(value).signal
        if parsed is not None:
            return float(parsed.initial_value)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "{} value {!r} is neither numeric nor a supported signal DSL".format(
                label,
                value,
            )
        ) from exc


class _Columns:
    def __init__(self, columns: Iterable[Any]):
        self._exact = {str(column): str(column) for column in columns}
        self._stripped: Dict[str, str] = {}
        for column in self._exact:
            self._stripped.setdefault(column.strip(), column)

    def find(self, candidates: Sequence[str]) -> Optional[str]:
        for candidate in candidates:
            if candidate in self._exact:
                return candidate
        for candidate in candidates:
            if candidate.strip() in self._stripped:
                return self._stripped[candidate.strip()]
        return None


def _row_value(
    row: Mapping[str, Any],
    columns: _Columns,
    candidates: Sequence[str],
) -> Tuple[Optional[str], Any]:
    for candidate in candidates:
        resolved = columns.find((candidate,))
        if resolved is not None and not _is_blank(row.get(resolved)):
            return resolved, row.get(resolved)
    return None, None


def _electrical_values(
    row: Mapping[str, Any],
    columns: _Columns,
    pbase_mw: Optional[float],
    qbase_mvar: Optional[float],
) -> Dict[str, float]:
    fault_column, fault_value = _row_value(
        row,
        columns,
        ("Grid_FL_MVA_sig", "Grid_FL_MVA"),
    )
    xr_column, xr_value = _row_value(
        row,
        columns,
        ("Grid_X2R_sig", "Grid_X2R", "Grid_XR"),
    )
    vpoc_column, vpoc_value = _row_value(
        row,
        columns,
        ("Vpoc_pu_sig", "Vpoc_pu"),
    )
    missing = [
        label
        for label, column in (
            ("fault level", fault_column),
            ("X/R", xr_column),
            ("initial Vpoc", vpoc_column),
        )
        if column is None
    ]
    if missing:
        raise ValueError("missing {}".format(", ".join(missing)))

    p_column, p_value = _row_value(
        row,
        columns,
        ("Ppoc_MW_sig", "Ppoc_MW", "P_POC_MW"),
    )
    if p_column is None:
        p_column, p_value = _row_value(row, columns, ("Ppoc_pu", "P_POC_PU"))
        if p_column is None or pbase_mw is None:
            raise ValueError(
                "missing Ppoc MW; provide Ppoc_MW_sig or pbase_mw with Ppoc_pu"
            )
        p_value = _initial_numeric(p_value, p_column) * float(pbase_mw)
    else:
        p_value = _initial_numeric(p_value, p_column)

    q_column, q_value = _row_value(
        row,
        columns,
        (
            "Qpoc_MVAr_init",
            "Qpoc_MVAr_sig",
            "Qpoc_MVAr",
            "Q_POC_MVAR",
        ),
    )
    if q_column is None:
        q_column, q_value = _row_value(row, columns, ("Qpoc_pu", "Q_POC_PU"))
        if q_column is None or qbase_mvar is None:
            raise ValueError(
                "missing Qpoc MVAr; provide Qpoc_MVAr_init/Qpoc_MVAr_sig "
                "or qbase_mvar with Qpoc_pu"
            )
        q_value = _initial_numeric(q_value, q_column) * float(qbase_mvar)
    else:
        q_value = _initial_numeric(q_value, q_column)

    _target_column, target_value = _row_value(row, columns, ("U_Ov",))
    target = 0.0 if _is_blank(target_value) else _initial_numeric(target_value, "U_Ov")
    return {
        "fault_level_mva": _initial_numeric(fault_value, str(fault_column)),
        "x_over_r": _initial_numeric(xr_value, str(xr_column)),
        "vpoc_pu": _initial_numeric(vpoc_value, str(vpoc_column)),
        "p_mw": float(p_value),
        "q_mvar": float(q_value),
        "target_v_poc_pu": float(target),
    }


def _normalise_key_number(value: float) -> str:
    if abs(float(value)) < 5e-13:
        value = 0.0
    return "{:.12g}".format(float(value))


def _cache_key(values: Mapping[str, float]) -> Tuple[str, ...]:
    return tuple(
        _normalise_key_number(values[name])
        for name in (
            "fault_level_mva",
            "x_over_r",
            "vpoc_pu",
            "p_mw",
            "q_mvar",
            "target_v_poc_pu",
        )
    )


def _numeric_or_none(value: Any) -> Optional[float]:
    if _is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cache_result(row: Mapping[str, Any], columns: _Columns) -> Dict[str, Optional[float]]:
    _column, vslack_value = _row_value(
        row,
        columns,
        ("constant_vslack_pu_sig", "Vslack_pu_sig"),
    )
    _column, tov_value = _row_value(row, columns, ("TOV_MVAr",))
    _column, capacitance_value = _row_value(
        row,
        columns,
        ("TOV_Shunt_C_uF_sig",),
    )
    return {
        "vslack": _numeric_or_none(vslack_value),
        "tov_mvar": _numeric_or_none(tov_value),
        "tov_capacitance_uf": _numeric_or_none(capacitance_value),
    }


def _same_optional_number(left: Optional[float], right: Optional[float]) -> bool:
    if left is None or right is None:
        return left is right
    scale = max(1.0, abs(left), abs(right))
    return abs(left - right) <= 1e-9 * scale


def _load_cache(
    path: Optional[Path],
    pbase_mw: Optional[float],
    qbase_mvar: Optional[float],
) -> Tuple[pd.DataFrame, Dict[Tuple[str, ...], Dict[str, Optional[float]]]]:
    if path is None or not path.is_file():
        return pd.DataFrame(), {}
    frame = pd.read_csv(path)
    columns = _Columns(frame.columns)
    values_by_key: Dict[Tuple[str, ...], Dict[str, Optional[float]]] = {}
    for number, row in frame.iterrows():
        try:
            electrical = _electrical_values(row, columns, pbase_mw, qbase_mvar)
        except ValueError as exc:
            raise ValueError(
                "Invalid Vslack cache row {} in {}: {}".format(number + 2, path, exc)
            ) from exc
        key = _cache_key(electrical)
        result = _cache_result(row, columns)
        previous = values_by_key.get(key)
        if previous is not None and any(
            not _same_optional_number(previous[name], result[name])
            for name in result
        ):
            raise ValueError(
                "Conflicting duplicate Vslack cache key at row {} in {}".format(
                    number + 2,
                    path,
                )
            )
        values_by_key[key] = result
    return frame, values_by_key


def _signal_with_vslack(raw_value: Any, vslack: float) -> Any:
    if isinstance(raw_value, str) and "$VSLACK" in raw_value:
        return raw_value.replace("$VSLACK", "{:.12g}".format(float(vslack)))
    return float(vslack)


def _cache_frame(
    entries: Mapping[Tuple[str, ...], Mapping[str, Optional[float]]],
    system_base_mva: float,
    pbase_mw: Optional[float],
    qbase_mvar: Optional[float],
    vbase_kv: float,
    fbase_hz: float,
) -> pd.DataFrame:
    rows = []
    for key in sorted(entries):
        result = entries[key]
        row = dict(zip(_KEY_COLUMNS, (float(value) for value in key)))
        row.update(
            {
                "constant_vslack_pu_sig": result.get("vslack"),
                "Vslack_pu_sig": result.get("vslack"),
                "TOV_MVAr": result.get("tov_mvar"),
                "TOV_Shunt_C_uF_sig": result.get("tov_capacitance_uf"),
                "System_Base_MVA": float(system_base_mva),
                "Plant_P_Base_MW": pbase_mw,
                "Plant_Q_Base_MVAr": qbase_mvar,
                "POC_Base_kV": float(vbase_kv),
                "Frequency_Hz": float(fbase_hz),
                "Cache_Format": 2,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _write_cache(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    frame.to_csv(temporary, index=False)
    os.replace(str(temporary), str(path))


def prepare_pscad_spec(
    spec: pd.DataFrame,
    *,
    use_vslack_cache: bool = False,
    calc_tov_shunt_var: bool = False,
    cache_path: Optional[str] = None,
    vbase_kv: float = 275.0,
    fbase_hz: float = 50.0,
    system_base_mva: float = 100.0,
    pbase_mw: Optional[float] = None,
    qbase_mvar: Optional[float] = None,
    update_cache: bool = True,
    verbose: bool = True,
) -> pd.DataFrame:
    """Populate PSCAD Vslack and TOV columns without Pallet.

    ``use_vslack_cache=False`` recalculates every Vslack and replaces the cache
    only after all rows succeed.  ``calc_tov_shunt_var=True`` recalculates TOV
    rows selected by ``Calc_TOV``; when that column contains no true values,
    rows with a positive ``U_Ov`` are selected.  With the TOV switch disabled,
    existing SPEC values are preserved and missing values may be filled from a
    compatible legacy cache.
    """
    if not isinstance(spec, pd.DataFrame):
        raise TypeError("spec must be a pandas DataFrame")
    result = spec.copy()
    if result.empty:
        result.attrs["pscad_initialisation"] = {
            "rows": 0,
            "vslack_cache_hits": 0,
            "vslack_calculated": 0,
            "tov_calculated": 0,
        }
        return result

    path = Path(cache_path).expanduser() if cache_path else None
    _old_cache, cached_entries = _load_cache(path, pbase_mw, qbase_mvar)
    cache_entries = dict(cached_entries) if use_vslack_cache else {}
    columns = _Columns(result.columns)
    electrical_rows = []
    for index, row in result.iterrows():
        try:
            electrical_rows.append(
                _electrical_values(row, columns, pbase_mw, qbase_mvar)
            )
        except ValueError as exc:
            identity = row.get("File_Name", index)
            raise ValueError(
                "Cannot initialise PSCAD SPEC row {!r}: {}".format(identity, exc)
            ) from exc

    calc_column = columns.find(("Calc_TOV",))
    requested_flags = (
        result[calc_column].map(_as_bool)
        if calc_column is not None
        else pd.Series(False, index=result.index)
    )
    use_explicit_tov_flags = bool(requested_flags.any())

    if "constant_vslack_pu_sig" not in result.columns:
        result["constant_vslack_pu_sig"] = pd.NA
    if "Vslack_pu_sig" not in result.columns:
        result["Vslack_pu_sig"] = pd.NA
    result["Vslack_pu_sig"] = result["Vslack_pu_sig"].astype(object)
    if "TOV_MVAr" not in result.columns:
        result["TOV_MVAr"] = pd.NA
    if "TOV_Shunt_C_uF_sig" not in result.columns:
        result["TOV_Shunt_C_uF_sig"] = pd.NA

    cache_hits = 0
    vslack_calculated = 0
    tov_calculated = 0
    tov_from_cache = 0
    for position, (index, row) in enumerate(result.iterrows()):
        electrical = electrical_rows[position]
        key = _cache_key(electrical)
        cached = cached_entries.get(key) if use_vslack_cache else None
        vslack = cached.get("vslack") if cached is not None else None
        if vslack is None:
            vslack = calculate_vslack_pu(
                electrical["fault_level_mva"],
                electrical["x_over_r"],
                electrical["vpoc_pu"],
                electrical["p_mw"],
                electrical["q_mvar"],
                system_base_mva,
            )
            vslack_calculated += 1
        else:
            cache_hits += 1
        result.at[index, "constant_vslack_pu_sig"] = float(vslack)
        result.at[index, "Vslack_pu_sig"] = _signal_with_vslack(
            row.get("Vslack_pu_sig"),
            float(vslack),
        )

        target_is_valid = electrical["target_v_poc_pu"] > 0
        tov_selected = bool(
            calc_tov_shunt_var
            and target_is_valid
            and (
                requested_flags.iloc[position]
                if use_explicit_tov_flags
                else True
            )
        )
        existing_tov = _numeric_or_none(row.get("TOV_MVAr"))
        existing_capacitance = _numeric_or_none(row.get("TOV_Shunt_C_uF_sig"))
        if tov_selected:
            tov_mvar = calculate_tov_shunt_mvar(
                electrical["fault_level_mva"],
                electrical["x_over_r"],
                electrical["vpoc_pu"],
                electrical["p_mw"],
                electrical["q_mvar"],
                electrical["target_v_poc_pu"],
                float(vslack),
                system_base_mva,
            )
            capacitance = shunt_mvar_to_capacitance_uf(
                tov_mvar,
                vbase_kv,
                fbase_hz,
            )
            tov_calculated += 1
        else:
            tov_mvar = existing_tov
            capacitance = existing_capacitance
            if cached is not None and tov_mvar is None:
                tov_mvar = cached.get("tov_mvar")
                if tov_mvar is not None:
                    tov_from_cache += 1
            if cached is not None and capacitance is None:
                capacitance = cached.get("tov_capacitance_uf")
            if tov_mvar is not None and capacitance is None:
                capacitance = shunt_mvar_to_capacitance_uf(
                    tov_mvar,
                    vbase_kv,
                    fbase_hz,
                )

        if tov_mvar is not None:
            result.at[index, "TOV_MVAr"] = float(tov_mvar)
        if capacitance is not None:
            result.at[index, "TOV_Shunt_C_uF_sig"] = float(capacitance)

        cache_entries[key] = {
            "vslack": float(vslack),
            "tov_mvar": tov_mvar,
            "tov_capacitance_uf": capacitance,
        }

    if update_cache and path is not None:
        _write_cache(
            path,
            _cache_frame(
                cache_entries,
                system_base_mva,
                pbase_mw,
                qbase_mvar,
                vbase_kv,
                fbase_hz,
            ),
        )

    summary = {
        "rows": len(result),
        "vslack_cache_hits": cache_hits,
        "vslack_calculated": vslack_calculated,
        "tov_calculated": tov_calculated,
        "tov_from_cache": tov_from_cache,
        "cache_path": str(path) if path is not None else None,
    }
    result.attrs["pscad_initialisation"] = summary
    if verbose:
        print(
            "PSCAD initialisation: {rows} rows; Vslack {vslack_cache_hits} cache / "
            "{vslack_calculated} calculated; TOV {tov_calculated} calculated / "
            "{tov_from_cache} cache".format(**summary)
        )
    return result
