"""Transparent PSCAD fault-code parsing used by several clause analyses."""

from __future__ import annotations

from typing import Mapping, Optional

from hbess_open.io.signal_dsl import ParsedDslSignal


DEFAULT_FAULT_CODE_NAMES = {
    0: "NONE",
    1: "LG",
    2: "LG",
    3: "LG",
    4: "LLG",
    5: "LLG",
    6: "LLG",
    7: "LLLG",
    8: "LL",
    9: "LL",
    10: "LL",
    11: "LLL",
}


_TEXT_ALIASES = {
    "1PHG": "LG",
    "LG": "LG",
    "2PHG": "LLG",
    "LLG": "LLG",
    "3PHG": "LLLG",
    "LLLG": "LLLG",
    "3PH": "LLL",
    "LLL": "LLL",
    "PHPH": "LL",
    "LL": "LL",
    "NOFAULT": "NONE",
    "NONE": "NONE",
}


def fault_code_value(value) -> Optional[int]:
    parsed = ParsedDslSignal.parse(value).signal
    if parsed is not None:
        targets = [piece.target for piece in parsed.pieces if float(piece.target) != 0.0]
        selected = targets[0] if targets else parsed.initial_value
        number = float(selected)
        if number.is_integer():
            return int(number)
    try:
        number = float(value)
        return int(number) if number.is_integer() else None
    except (TypeError, ValueError):
        return None


def fault_code_name(value, names: Optional[Mapping[int, str]] = None) -> str:
    code = fault_code_value(value)
    if code is not None:
        return str(dict(names or DEFAULT_FAULT_CODE_NAMES).get(code, "CODE_{}".format(code)))
    text = str(value).strip().upper().replace(" ", "")
    return _TEXT_ALIASES.get(text, str(value))
