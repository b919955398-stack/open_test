from __future__ import annotations

import math
from typing import Tuple

from hbess_open.initialisation.grid_equivalent import (
    impedance_from_fault_level as _impedance_from_fault_level,
    infinite_bus_voltage as _infinite_bus_voltage,
)


def impedance_from_fault_level(
    fault_level_mva: float,
    x_over_r: float,
    psse_base_mva: float = 100.0,
) -> Tuple[float, float]:
    """Return Thevenin R/X in pu on the PSS/E system base."""
    return _impedance_from_fault_level(
        fault_level_mva,
        x_over_r,
        psse_base_mva,
    )


def impedance_from_scr(
    scr: float,
    plant_base_mva: float,
    x_over_r: float,
    psse_base_mva: float = 100.0,
) -> Tuple[float, float]:
    return impedance_from_fault_level(
        float(scr) * float(plant_base_mva),
        x_over_r,
        psse_base_mva,
    )


def infinite_bus_voltage(
    v_poc_pu: float,
    p_mw: float,
    q_mvar: float,
    r_pu: float,
    x_pu: float,
    psse_base_mva: float = 100.0,
) -> float:
    """Back-calculate infinite-bus voltage using the open DMAT convention."""
    return _infinite_bus_voltage(
        v_poc_pu,
        p_mw,
        q_mvar,
        r_pu,
        x_pu,
        psse_base_mva,
    )


def fault_impedance_ohm(
    source_r_ohm: float,
    source_x_ohm: float,
    zf_over_zs: float = 0.0,
    fault_x_over_r: float = 0.0,
    r_offset_ohm: float = 0.0,
    x_offset_ohm: float = 0.0,
    residual_voltage_pu=None,
) -> Tuple[float, float]:
    source_magnitude = abs(complex(float(source_r_ohm), float(source_x_ohm)))
    ratio = float(zf_over_zs or 0.0)
    if residual_voltage_pu not in (None, "") and ratio == 0.0:
        ures = float(residual_voltage_pu)
        if not 0.0 <= ures < 1.0:
            raise ValueError("Residual voltage must be in [0, 1)")
        ratio = 0.0 if ures == 0.0 else ures / (1.0 - ures)
    z_fault = source_magnitude * ratio
    xr = float(fault_x_over_r or 0.0)
    if xr == 0.0:
        r_fault, x_fault = z_fault, 0.0
    else:
        r_fault = z_fault / math.sqrt(1.0 + xr * xr)
        x_fault = r_fault * xr
    return r_fault + float(r_offset_ohm or 0.0), x_fault + float(x_offset_ohm or 0.0)
