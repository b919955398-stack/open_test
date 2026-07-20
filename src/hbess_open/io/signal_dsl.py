"""Parser for the signal DSL used by the Heywood SPEC workbooks.

This is the small, transparent replacement for ``pallet.dsl.ParsedDslSignal``.
It intentionally exposes the same data needed by the clause analyses: an
initial value and event pieces containing ``time_start`` and ``target``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple


NUMBER = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"


@dataclass(frozen=True)
class SignalPiece:
    time_start: float
    target: float
    time_end: Optional[float] = None


@dataclass(frozen=True)
class Signal:
    initial_value: float
    pieces: Tuple[SignalPiece, ...]
    scaling: float = 1.0


@dataclass(frozen=True)
class ParsedSignal:
    signal: Optional[Signal]

    @classmethod
    def parse(cls, value) -> "ParsedSignal":
        if value is None or value == "":
            return cls(None)
        if isinstance(value, (int, float)):
            return cls(Signal(float(value), ()))

        source = str(value).strip().replace("WITH SCALING =", "WITH SCALING=")
        initial_match = re.match(r"\s*({})".format(NUMBER), source, re.IGNORECASE)
        if initial_match is None:
            return cls(None)

        scale_match = re.search(
            r"WITH\s+SCALING\s*=\s*({})".format(NUMBER), source, re.IGNORECASE
        )
        scale = float(scale_match.group(1)) if scale_match else 1.0
        pieces = []
        event_re = re.compile(
            r"FROM\s+({n})\s*s\s+TO\s+({n})\s*s\s*[,;]?\s*[^\d+\-]*\s*({n})"
            r"|AT\s+({n})\s*s\s*[,;]?\s*[^\d+\-]*\s*({n})".format(n=NUMBER),
            re.IGNORECASE,
        )
        for match in event_re.finditer(source):
            if match.group(1) is not None:
                start = float(match.group(1))
                end = float(match.group(2))
                target = float(match.group(3)) * scale
                pieces.append(SignalPiece(start, target, end))
            else:
                start = float(match.group(4))
                target = float(match.group(5)) * scale
                pieces.append(SignalPiece(start, target))

        return cls(
            Signal(
                initial_value=float(initial_match.group(1)) * scale,
                pieces=tuple(pieces),
                scaling=scale,
            )
        )


# Explicit compatibility alias used while ported clause code is reviewed.
ParsedDslSignal = ParsedSignal
