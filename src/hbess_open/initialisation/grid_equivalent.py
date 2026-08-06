"""Transparent two-bus calculations used by PSS/E and PSCAD initialisation.

The original workflow delegated these calculations to Pallet/pandapower.  The
equations below expose the complete electrical convention: positive P and Q
are injections from the POC into a Thevenin grid represented by ``R + jX``.
"""

from __future__ import annotations

import cmath
import math
from typing import List, Optional, Tuple


def impedance_from_fault_level(
    fault_level_mva: float,
    x_over_r: float,
    system_base_mva: float = 100.0,
) -> Tuple[float, float]:
    """Return Thevenin R/X in pu on ``system_base_mva``."""
    fault_level_mva = float(fault_level_mva)
    x_over_r = float(x_over_r)
    system_base_mva = float(system_base_mva)
    if fault_level_mva <= 0:
        raise ValueError("fault_level_mva must be positive")
    if x_over_r < 0:
        raise ValueError("x_over_r cannot be negative")
    if system_base_mva <= 0:
        raise ValueError("system_base_mva must be positive")
    z_pu = system_base_mva / fault_level_mva
    r_pu = z_pu / math.sqrt(1.0 + x_over_r * x_over_r)
    return r_pu, r_pu * x_over_r


def impedance_from_scr(
    scr: float,
    plant_base_mva: float,
    x_over_r: float,
    system_base_mva: float = 100.0,
) -> Tuple[float, float]:
    return impedance_from_fault_level(
        float(scr) * float(plant_base_mva),
        x_over_r,
        system_base_mva,
    )


def infinite_bus_phasor(
    v_poc_pu: float,
    p_mw: float,
    q_mvar: float,
    r_pu: float,
    x_pu: float,
    system_base_mva: float = 100.0,
) -> complex:
    """Back-calculate the infinite-bus phasor with the POC angle set to zero."""
    v_poc_pu = float(v_poc_pu)
    system_base_mva = float(system_base_mva)
    if v_poc_pu <= 0:
        raise ValueError("v_poc_pu must be positive")
    if system_base_mva <= 0:
        raise ValueError("system_base_mva must be positive")
    s_conjugate_pu = complex(float(p_mw), -float(q_mvar)) / system_base_mva
    return complex(v_poc_pu, 0.0) - (
        s_conjugate_pu * complex(float(r_pu), float(x_pu)) / v_poc_pu
    )


def infinite_bus_voltage(
    v_poc_pu: float,
    p_mw: float,
    q_mvar: float,
    r_pu: float,
    x_pu: float,
    system_base_mva: float = 100.0,
) -> float:
    """Return the magnitude of :func:`infinite_bus_phasor`."""
    return abs(
        infinite_bus_phasor(
            v_poc_pu,
            p_mw,
            q_mvar,
            r_pu,
            x_pu,
            system_base_mva,
        )
    )


def calculate_vslack_pu(
    fault_level_mva: float,
    x_over_r: float,
    v_poc_pu: float,
    p_mw: float,
    q_mvar: float,
    system_base_mva: float = 100.0,
) -> float:
    """Calculate the constant Vslack magnitude for one operating point.

    A non-positive fault level is treated as the SPEC's zero-impedance grid
    marker, for which Vslack equals the requested POC voltage.
    """
    if float(fault_level_mva) <= 0:
        return float(v_poc_pu)
    r_pu, x_pu = impedance_from_fault_level(
        fault_level_mva,
        x_over_r,
        system_base_mva,
    )
    return infinite_bus_voltage(
        v_poc_pu,
        p_mw,
        q_mvar,
        r_pu,
        x_pu,
        system_base_mva,
    )


def _candidate_angles(
    voltage_pu: float,
    vslack_pu: float,
    active_power_pu: float,
    r_pu: float,
    x_pu: float,
) -> List[float]:
    """Return both two-bus voltage-angle roots for fixed |V|, |E| and P."""
    voltage_pu = float(voltage_pu)
    vslack_pu = float(vslack_pu)
    denominator = float(r_pu) ** 2 + float(x_pu) ** 2
    if voltage_pu <= 0 or vslack_pu <= 0:
        raise ValueError("voltage_pu and vslack_pu must be positive")
    if denominator == 0:
        raise ValueError("Thevenin impedance cannot be zero for a TOV calculation")

    conductance = float(r_pu) / denominator
    susceptance = float(x_pu) / denominator
    admittance_magnitude = math.hypot(conductance, susceptance)
    rhs = (
        voltage_pu * voltage_pu * conductance - float(active_power_pu)
    ) / (voltage_pu * vslack_pu * admittance_magnitude)
    tolerance = 1e-10
    if rhs < -1.0 - tolerance or rhs > 1.0 + tolerance:
        raise ValueError(
            "No two-bus operating point exists for V={:.12g} pu, "
            "Vslack={:.12g} pu and P={:.12g} pu".format(
                voltage_pu,
                vslack_pu,
                active_power_pu,
            )
        )
    rhs = max(-1.0, min(1.0, rhs))
    alpha = math.acos(rhs)
    impedance_angle = math.atan2(susceptance, conductance)
    return [alpha - impedance_angle, -alpha - impedance_angle]


def _reactive_power_pu(
    voltage_pu: float,
    voltage_angle_rad: float,
    vslack_pu: float,
    r_pu: float,
    x_pu: float,
) -> float:
    denominator = float(r_pu) ** 2 + float(x_pu) ** 2
    conductance = float(r_pu) / denominator
    susceptance = float(x_pu) / denominator
    voltage_pu = float(voltage_pu)
    angle = float(voltage_angle_rad)
    return (
        voltage_pu * voltage_pu * susceptance
        - voltage_pu
        * float(vslack_pu)
        * (
            conductance * math.sin(angle)
            + susceptance * math.cos(angle)
        )
    )


def _nearest_equivalent_angle(angle: float, reference: float) -> float:
    return float(angle) + 2.0 * math.pi * round(
        (float(reference) - float(angle)) / (2.0 * math.pi)
    )


def calculate_tov_shunt_mvar(
    fault_level_mva: float,
    x_over_r: float,
    v_poc_pu: float,
    p_mw: float,
    q_mvar: float,
    target_v_poc_pu: float,
    vslack_pu: Optional[float] = None,
    system_base_mva: float = 100.0,
) -> float:
    """Return nominal shunt MVAr required to reach ``target_v_poc_pu``.

    The plant P and Q are held at their initial values.  The selected solution
    is the high-voltage branch closest to the initial operating point.  A
    positive result is a capacitive bank rating at 1.0 pu.  Its actual reactive
    injection at the target voltage is ``rating * target_v_poc_pu**2``.  This
    matches pandapower's shunt convention used by the former Pallet helper and
    allows the returned value to convert directly to capacitance at ``Vbase``.
    """
    system_base_mva = float(system_base_mva)
    if system_base_mva <= 0:
        raise ValueError("system_base_mva must be positive")
    r_pu, x_pu = impedance_from_fault_level(
        fault_level_mva,
        x_over_r,
        system_base_mva,
    )
    calculated_phasor = infinite_bus_phasor(
        v_poc_pu,
        p_mw,
        q_mvar,
        r_pu,
        x_pu,
        system_base_mva,
    )
    slack_magnitude = (
        abs(calculated_phasor) if vslack_pu is None else float(vslack_pu)
    )
    p_pu = float(p_mw) / system_base_mva
    q_pu = float(q_mvar) / system_base_mva

    initial_candidates = _candidate_angles(
        v_poc_pu,
        slack_magnitude,
        p_pu,
        r_pu,
        x_pu,
    )
    phasor_reference = -cmath.phase(calculated_phasor)
    initial_angles = [
        _nearest_equivalent_angle(angle, phasor_reference)
        for angle in initial_candidates
    ]
    initial_angle = min(
        initial_angles,
        key=lambda angle: abs(
            _reactive_power_pu(
                v_poc_pu,
                angle,
                slack_magnitude,
                r_pu,
                x_pu,
            )
            - q_pu
        ),
    )

    target_angles = [
        _nearest_equivalent_angle(angle, initial_angle)
        for angle in _candidate_angles(
            target_v_poc_pu,
            slack_magnitude,
            p_pu,
            r_pu,
            x_pu,
        )
    ]
    target_angle = min(
        target_angles,
        key=lambda angle: abs(angle - initial_angle),
    )
    total_q_pu = _reactive_power_pu(
        target_v_poc_pu,
        target_angle,
        slack_magnitude,
        r_pu,
        x_pu,
    )
    actual_injection_mvar = (total_q_pu - q_pu) * system_base_mva
    target_voltage = float(target_v_poc_pu)
    result = actual_injection_mvar / (target_voltage * target_voltage)
    return 0.0 if abs(result) < 1e-10 else result


def shunt_mvar_to_capacitance_uf(
    shunt_mvar: float,
    vbase_kv: float,
    fbase_hz: float = 50.0,
) -> float:
    """Convert three-phase shunt MVAr to the legacy SPEC capacitance in uF."""
    vbase_kv = float(vbase_kv)
    fbase_hz = float(fbase_hz)
    if vbase_kv <= 0 or fbase_hz <= 0:
        raise ValueError("vbase_kv and fbase_hz must be positive")
    return float(shunt_mvar) * 1e6 / (
        2.0 * math.pi * fbase_hz * vbase_kv * vbase_kv
    )
