from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import PlaybackPoint


NUMBER = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"


def parse_signal_profile(text, step_epsilon: float = 0.001) -> List[Tuple[float, float]]:
    """Parse HY human-readable signal strings into piecewise-linear points."""
    if text in (None, ""):
        return []
    if isinstance(text, (int, float)):
        return [(0.0, float(text))]
    source = str(text).replace("WITH SCALING =", "WITH SCALING=")
    first = re.match(r"\s*({})".format(NUMBER), source, re.IGNORECASE)
    if not first:
        return []
    scale_match = re.search(r"WITH\s+SCALING\s*=\s*({})".format(NUMBER), source, re.IGNORECASE)
    scale = float(scale_match.group(1)) if scale_match else 1.0
    points: List[Tuple[float, float]] = [(0.0, float(first.group(1)) * scale)]
    current = points[0][1]
    token_re = re.compile(
        r"FROM\s+({n})\s*s\s+TO\s+({n})\s*s\s*[,;]?\s*[^\d+\-]*\s*({n})"
        r"|AT\s+({n})\s*s\s*[,;]?\s*[^\d+\-]*\s*({n})".format(n=NUMBER),
        re.IGNORECASE,
    )
    for match in token_re.finditer(source):
        if match.group(1) is not None:
            start, end, target = float(match.group(1)), float(match.group(2)), float(match.group(3)) * scale
            points.append((start, current))
            points.append((end, target))
            current = target
        else:
            at, target = float(match.group(4)), float(match.group(5)) * scale
            points.append((max(0.0, at - step_epsilon), current))
            points.append((at, target))
            current = target
    dedup: Dict[float, float] = {}
    for time, value in points:
        dedup[float(time)] = float(value)
    return sorted(dedup.items())


def initial_signal_value(value, default=None) -> float:
    """Return the time-zero value from a numeric value or signal profile.

    HY SPEC steady-state columns can contain a complete dynamic profile, for
    example ``285, AT 5s ↓ 142.5``.  Dispatch must use only the first value;
    the later points are applied separately by the compiled dynamic commands.
    """
    source = default if value in (None, "") else value
    if source in (None, ""):
        raise ValueError("Signal value is missing")
    points = parse_signal_profile(source)
    if points:
        return float(points[0][1])
    return float(source)


def _interpolate(points: Sequence[Tuple[float, float]], time: float) -> Optional[float]:
    if not points:
        return None
    if time <= points[0][0]:
        return points[0][1]
    for left, right in zip(points, points[1:]):
        if left[0] <= time <= right[0]:
            if right[0] == left[0]:
                return right[1]
            fraction = (time - left[0]) / (right[0] - left[0])
            return left[1] + fraction * (right[1] - left[1])
    return points[-1][1]


def combine_playback(voltage: Iterable[Tuple[float, float]], frequency: Iterable[Tuple[float, float]]) -> List[PlaybackPoint]:
    voltage_points, frequency_points = list(voltage), list(frequency)
    times = sorted({point[0] for point in voltage_points + frequency_points})
    return [
        PlaybackPoint(time, _interpolate(voltage_points, time), _interpolate(frequency_points, time))
        for time in times
    ]
