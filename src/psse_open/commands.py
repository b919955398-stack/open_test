from __future__ import annotations

import re
from typing import Any, Dict, List

from .models import Event, Scenario, StudyPlan
from .profiles import combine_playback, initial_signal_value, parse_signal_profile
from .grid import impedance_from_fault_level, infinite_bus_voltage


NUMBER = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"


def _number(value: Any, default=None):
    if value in (None, ""):
        return default
    return float(value)


def _first_number(scenario: Scenario, names, default=None):
    for name in names:
        value = scenario.get(name)
        if value not in (None, ""):
            return _number(value, default)
    return default


def _initial_profile_value(value: Any, default: float = 0.0) -> float:
    return initial_signal_value(value, default)


def resolve_vslack_expression(scenario: Scenario, expression: Any) -> Any:
    """Resolve HY's `$VSLACK` token without importing PSS/E or Pallet."""
    if not isinstance(expression, str) or "$VSLACK" not in expression:
        return expression
    pbase = _initial_profile_value(scenario.get("Pbase_MW"), 285.0)
    qbase = _initial_profile_value(scenario.get("Qbase_MVAr"), 112.575)
    vpoc = _initial_profile_value(scenario.get("Vpoc_pu_sig"), 1.06)
    p_mw = _initial_profile_value(
        scenario.get("Ppoc_MW_sig"), _initial_profile_value(scenario.get("Ppoc_pu"), 0.0) * pbase
    )
    q_mvar = _initial_profile_value(
        scenario.get("Qpoc_MVAr_init"), _initial_profile_value(scenario.get("Qpoc_pu"), 0.0) * qbase
    )
    if str(scenario.get("Grid_SCR", "")).upper() == "ZERO_IMP":
        vslack = vpoc
    else:
        fault_level = _initial_profile_value(scenario.get("Grid_FL_MVA_sig"), 0.0)
        if fault_level <= 0.0:
            fault_level = _initial_profile_value(scenario.get("Grid_SCR"), 0.0) * pbase
        r_pu, x_pu = impedance_from_fault_level(
            fault_level, _initial_profile_value(scenario.get("Grid_X2R_sig"), 0.0)
        )
        vslack = infinite_bus_voltage(vpoc, p_mw, q_mvar, r_pu, x_pu)
    return expression.replace("$VSLACK", "{:.12g}".format(vslack))


def parse_psse_commands(text: str) -> List[Event]:
    """Parse the command language visible in HY SPEC into explicit events."""
    if not text:
        return []
    events: List[Event] = []
    order = 0
    source = str(text)

    model_set = re.compile(
        r"SET\s+MODEL\s+['\"]([^'\"]+)['\"]\s+(ICON|CON|VAR)\s+(\d+)\s+TO\s+({n})\s+AT\s+({n})s".format(n=NUMBER),
        re.IGNORECASE,
    )
    for match in model_set.finditer(source):
        events.append(Event(float(match.group(5)), order, "model_change", {
            "model": match.group(1), "item": match.group(2).upper(), "index": int(match.group(3)), "value": float(match.group(4))
        }, "PSSE Commands"))
        order += 1

    drive = re.compile(
        r"DRIVE\s+MODEL\s+['\"]([^'\"]+)['\"]\s+(ICON|CON|VAR)\s+(\d+)\s*=\s*([^;]+)",
        re.IGNORECASE,
    )
    drive_point = re.compile(r"AT\s+({n})s\s*[^,;\d+-]*\s*({n})".format(n=NUMBER), re.IGNORECASE)
    scale_re = re.compile(r"WITH\s+SCALING\s*=\s*({})".format(NUMBER), re.IGNORECASE)
    for match in drive.finditer(source):
        body = match.group(4)
        scale_match = scale_re.search(body)
        scale = float(scale_match.group(1)) if scale_match else 1.0
        for point in drive_point.finditer(body):
            events.append(Event(float(point.group(1)), order, "model_change", {
                "model": match.group(1), "item": match.group(2).upper(), "index": int(match.group(3)),
                "value": float(point.group(2)), "declared_scaling": scale,
            }, "PSSE Commands"))
            order += 1

    branch = re.compile(
        r"CHANGE\s+BRANCH\s+['\"]([^'\"]+)['\"]\s+FAULT_LEVEL\s+AND\s+X2R\s+TO\s+({n})\s+AND\s+({n})\s+AT\s+({n})s".format(n=NUMBER),
        re.IGNORECASE,
    )
    for match in branch.finditer(source):
        events.append(Event(float(match.group(4)), order, "grid_strength", {
            "branch": match.group(1), "fault_level_mva": float(match.group(2)), "x_over_r": float(match.group(3))
        }, "PSSE Commands"))
        order += 1

    fault = re.compile(
        r"APPLY\s+FAULT\s+TO\s+BUS\s+['\"]([^'\"]+)['\"]\s+AT\s+({n})s\s+WITH\s+TYPE=({n}),\s*X2R=({n}),\s*ZF2ZS=({n}),\s*(?:URES_PU=({n}),\s*)?RF_OFFSET=({n}),\s*XF_OFFSET=({n}),\s*DURATION=({n})s".format(n=NUMBER),
        re.IGNORECASE,
    )
    for match in fault.finditer(source):
        start, duration = float(match.group(2)), float(match.group(9))
        payload = {
            "bus": match.group(1), "type_code": int(float(match.group(3))), "fault_x_over_r": float(match.group(4)),
            "zf_over_zs": float(match.group(5)), "r_offset_ohm": float(match.group(7)), "x_offset_ohm": float(match.group(8)),
        }
        if match.group(6) is not None:
            payload["residual_voltage_pu"] = float(match.group(6))
        events.append(Event(start, order, "fault_apply", payload, "PSSE Commands")); order += 1
        events.append(Event(start + duration, order, "fault_clear", {}, "PSSE Commands")); order += 1

    load_change = re.compile(
        r"CHANGE\s+LOAD\s+['\"]([^'\"]+)['\"]\s+(MW|MVAR)\s+TO\s+({n})\s+AT\s+({n})s".format(n=NUMBER),
        re.IGNORECASE,
    )
    for match in load_change.finditer(source):
        events.append(Event(float(match.group(4)), order, "load_change", {
            "load": match.group(1), "quantity": match.group(2).upper(), "value": float(match.group(3))
        }, "PSSE Commands"))
        order += 1

    fixed_shunt_change = re.compile(
        r"CHANGE\s+FIXED_SHUNT\s+['\"]([^'\"]+)['\"]\s+MVAR\s+TO\s+({n})\s+AT\s+({n})\s*s\b".format(
            n=NUMBER
        ),
        re.IGNORECASE,
    )
    for match in fixed_shunt_change.finditer(source):
        events.append(Event(float(match.group(3)), order, "fixed_shunt_change", {
            "shunt": match.group(1), "mvar": float(match.group(2))
        }, "PSSE Commands"))
        order += 1

    fixed_shunt_trip = re.compile(
        r"TRIP\s+FIXED_SHUNT\s+['\"]([^'\"]+)['\"]\s+AT\s+({n})\s*s\b".format(
            n=NUMBER
        ),
        re.IGNORECASE,
    )

    fixed_shunt_commands = [
        command.strip()
        for command in re.split(r";|[\r\n]+", source)
        if re.search(r"\bFIXED_SHUNT\b", command, re.IGNORECASE)
    ]
    for command in fixed_shunt_commands:
        if not (
            fixed_shunt_change.fullmatch(command)
            or fixed_shunt_trip.fullmatch(command)
        ):
            raise ValueError(
                "Invalid FIXED_SHUNT command syntax in PSSE Commands: {!r}. "
                "Expected CHANGE FIXED_SHUNT '<name>' MVAR TO <value> AT <time>s "
                "or TRIP FIXED_SHUNT '<name>' AT <time>s.".format(command)
            )

    for match in fixed_shunt_trip.finditer(source):
        events.append(Event(float(match.group(2)), order, "fixed_shunt_trip", {
            "shunt": match.group(1)
        }, "PSSE Commands"))
        order += 1

    transformer = re.compile(
        r"CHANGE\s+TRANSFORMER\s+['\"]([^'\"]+)['\"]\s+PHASE\s+TO\s+({n})\s+AT\s+({n})s".format(n=NUMBER),
        re.IGNORECASE,
    )
    for match in transformer.finditer(source):
        events.append(Event(float(match.group(3)), order, "transformer_phase", {
            "transformer": match.group(1), "phase_deg": float(match.group(2))
        }, "PSSE Commands"))
        order += 1
    return sorted(events)


def _structured_fault(scenario: Scenario, order: int = 0) -> List[Event]:
    start = _number(scenario.get("Fault_Time_sig"))
    duration = _number(scenario.get("Fault_Duration_sig"))
    type_code = scenario.get("Fault_Type_sig")
    if start is None or duration is None or type_code is None:
        return []
    payload = {
        "bus": scenario.get("Faulted_Bus", "fault"),
        "type_code": int(type_code),
        "fault_x_over_r": _number(scenario.get("Fault_X2R_sig"), _number(scenario.get("Grid_X2R_sig"), 0.0)),
        "zf_over_zs": _number(scenario.get("Zf2Zs_sig"), 0.0),
        "r_offset_ohm": _number(scenario.get("Rf_Offset_sig"), 0.0),
        "x_offset_ohm": _number(scenario.get("Xf_Offset_sig"), 0.0),
        "residual_voltage_pu": scenario.get("Ures_sig"),
    }
    return [
        Event(start, order, "fault_apply", payload),
        Event(start + duration, order + 1, "fault_clear", {}),
    ]


def _legacy_mfrt(scenario: Scenario) -> List[Event]:
    profile = scenario.get("MFRT_profile", [])
    if not isinstance(profile, (list, tuple)):
        return []
    result: List[Event] = []
    fault_codes = {"3PH": 7, "3PHG": 7, "SLG": 1, "1PHG": 1, "2LG": 4, "2PHG": 4, "LL": 8, "1PHPH": 8}
    for order, entry in enumerate(profile):
        if len(entry) != 4:
            continue
        start, end, zfactor, kind = entry
        result.append(Event(float(start), 2 * order, "fault_apply", {
            "bus": "fault", "type_code": fault_codes.get(str(kind).upper(), 7),
            "fault_x_over_r": _number(scenario.get("Grid_X2R_sig"), 0.0), "zf_over_zs": float(zfactor),
            "r_offset_ohm": 0.0, "x_offset_ohm": 0.0,
        }, "MFRT_profile"))
        result.append(Event(float(end), 2 * order + 1, "fault_clear", {}, "MFRT_profile"))
    return result


def build_plan(scenario: Scenario) -> StudyPlan:
    warnings: List[str] = []
    commands = scenario.get("PSSE Commands")
    events = parse_psse_commands(str(commands)) if commands else []
    if not events:
        events.extend(_structured_fault(scenario))
        events.extend(_legacy_mfrt(scenario))
    if scenario.get("Phase_Step_deg") not in (None, "") and not any(event.kind == "transformer_phase" for event in events):
        events.append(Event(_number(scenario.get("fstart"), 1.0), len(events), "transformer_phase", {
            "transformer": "phase_shift_tx", "phase_deg": float(scenario.get("Phase_Step_deg"))
        }))

    voltage_text = resolve_vslack_expression(
        scenario, scenario.get("Vslack_pu_psse", scenario.get("Vslack_pu_sig"))
    )
    frequency_text = scenario.get("Fslack_Hz_sig")
    voltage = parse_signal_profile(voltage_text)
    frequency = parse_signal_profile(frequency_text)
    playback = combine_playback(voltage, frequency)

    if scenario.get("PLB_Required") is True and not playback:
        warnings.append("PLB_Required is true but no parseable Vslack/Fslack profile was found")
    tov_capacitance = scenario.get("TOV_Shunt_C_uF_sig")
    tov_mvar = scenario.get("TOV_MVAr")
    if tov_capacitance not in (None, "") or tov_mvar not in (None, ""):
        start = _first_number(
            scenario, ("Fault_Time", "Fault_Time_sig", "fstart"), 0.5
        )
        duration = _first_number(
            scenario, ("Fault_Duration", "Fault_Duration_sig", "fdur"), 0.43
        )
        payload = {"bus": scenario.get("Faulted_Bus", "poc")}
        if tov_capacitance not in (None, ""):
            payload["capacitance_uf"] = float(tov_capacitance)
        else:
            payload["mvar"] = float(tov_mvar)
        events.append(
            Event(start, len(events), "tov_shunt_apply", payload, "structured TOV")
        )
        events.append(
            Event(
                start + duration,
                len(events),
                "tov_shunt_clear",
                {"bus": scenario.get("Faulted_Bus", "poc")},
                "structured TOV",
            )
        )

    callbacks = scenario.get("Active Callbacks")
    if callbacks not in (None, ""):
        names = callbacks if isinstance(callbacks, (list, tuple)) else re.split(r"[,;]", str(callbacks))
        for name in names:
            if str(name).strip():
                events.append(Event(0.0, len(events), "callback", {"name": str(name).strip()}))

    events.sort()
    if events and events[-1].time > scenario.end_time:
        warnings.append("Last event at {:.3f}s exceeds end time {:.3f}s".format(events[-1].time, scenario.end_time))
    return StudyPlan(scenario, events, playback, warnings)
