"""Rise, settling, recovery and damping metrics for one disturbance.

The public dataclasses and ``analyse_step`` signature follow the supplied
GridLink source. The implementation adds validation and handles monotonic or
short signals without uninitialised variables/divide-by-zero failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd


NOT_FOUND = 9999.0


@dataclass
class SettleTimeResults:
    settled_time: float
    settling_time_sec: float
    upper_limit: float
    lower_limit: float


@dataclass
class CommencementTimeResults:
    commencement_time_sec: float


@dataclass
class PRecoveryTimeResults:
    recovered_time: Optional[float]
    p_recovery_time_sec: Optional[float]
    p_recovery_threshold: Optional[float]


@dataclass
class RiseTimeResults:
    rise_time_sec: float
    lower_limit: float
    upper_limit: float
    lower_limit_time_sec: float
    upper_limit_time_sec: float
    commencement_time_sec: float


@dataclass
class StepAnalysisResults:
    start_time: float
    initial_value: float
    final_value: float
    min_value: float
    max_value: float
    largest_change: float
    largest_change_direction: int
    rise_time_results: RiseTimeResults
    p_recovery_time_results: PRecoveryTimeResults
    settling_time_results: SettleTimeResults
    halving_time_sec: float
    damping_ratio: float
    CommencementTimeResults: CommencementTimeResults


def _clean(series: pd.Series) -> pd.Series:
    result = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    result.index = pd.to_numeric(result.index, errors="raise")
    if len(result) < 2:
        raise ValueError("Step analysis requires at least two numeric samples")
    return result


def _first_crossing(series: pd.Series, level: float, direction: int) -> float:
    selected = series[series * direction >= level * direction]
    return float(selected.index[0]) if not selected.empty else NOT_FOUND


def rise_time(series, initial_value, final_value, largest_change_direction):
    step_size = final_value - initial_value
    reference_change = step_size
    if abs(reference_change) < np.finfo(float).eps:
        reference_change = float(series.iloc[-1] - series.iloc[0])
    lower_limit = initial_value + 0.1 * reference_change
    upper_limit = initial_value + 0.9 * reference_change
    lower_time = _first_crossing(series, lower_limit, largest_change_direction)
    upper_time = _first_crossing(series, upper_limit, largest_change_direction)
    rise_sec = upper_time - lower_time if lower_time < NOT_FOUND and upper_time < NOT_FOUND else NOT_FOUND
    commencement = lower_time - float(series.index[0]) if lower_time < NOT_FOUND else NOT_FOUND
    return RiseTimeResults(rise_sec, lower_limit, upper_limit, lower_time, upper_time, commencement)


def settle_time(series, start_time, initial_value, final_value, largest_change):
    step_size = final_value - initial_value
    reference = largest_change if abs(step_size) < 0.5 * abs(largest_change) else step_size
    tolerance = max(0.1 * abs(reference), np.finfo(float).eps)
    lower_limit, upper_limit = final_value - tolerance, final_value + tolerance
    inside = ((series >= lower_limit) & (series <= upper_limit)).to_numpy()
    suffix_all_inside = np.logical_and.accumulate(inside[::-1])[::-1]
    indexes = np.flatnonzero(suffix_all_inside)
    if len(indexes):
        settled_time = float(series.index[indexes[0]])
        settling_sec = settled_time - float(start_time)
    else:
        settled_time = settling_sec = NOT_FOUND
    return SettleTimeResults(settled_time, settling_sec, upper_limit, lower_limit)


def p_recovery_time(series, start_time, recovery_target_mw=None, select_first_recovery=True):
    if recovery_target_mw is None:
        return PRecoveryTimeResults(None, None, None)
    target = float(recovery_target_mw)
    reached = series >= target if target >= 0 else series <= target
    indexes = np.flatnonzero(reached.to_numpy())
    if not len(indexes):
        return PRecoveryTimeResults(NOT_FOUND, NOT_FOUND, target)
    index = indexes[0] if select_first_recovery else indexes[-1]
    recovered = float(series.index[index])
    return PRecoveryTimeResults(recovered, recovered - float(start_time), target)


def commencement_time(
    series: pd.Series,
    series2: pd.Series,
    initial_value,
    final_value,
    largest_change_direction,
    commencement_thresholds: Optional[List[float]] = None,
):
    response_level = initial_value + 0.1 * (final_value - initial_value)
    response_time = _first_crossing(series, response_level, largest_change_direction)
    trigger_time = float(series.index[0])
    if commencement_thresholds and len(commencement_thresholds) >= 2:
        low, high = sorted(float(item) for item in commencement_thresholds[:2])
        outside = series2[(series2 <= low) | (series2 >= high)]
        if not outside.empty:
            trigger_time = float(outside.index[0])
    delay = max(0.0, response_time - trigger_time) if response_time < NOT_FOUND else NOT_FOUND
    return CommencementTimeResults(delay)


def get_final_value(series: pd.Series) -> float:
    series = _clean(series)
    count = max(1, int(round(len(series) * 0.1)))
    return float(series.iloc[-count:].mean())


def get_freq(series: pd.Series) -> float:
    series = _clean(series)
    time = series.index.to_numpy(dtype=float)
    dt = float(np.median(np.diff(time)))
    if dt <= 0:
        return 0.0
    values = series.to_numpy(dtype=float) - float(series.mean())
    magnitudes = np.abs(np.fft.rfft(values))
    frequencies = np.fft.rfftfreq(len(values), d=dt)
    if len(magnitudes) <= 1 or np.allclose(magnitudes[1:], 0):
        return 0.0
    return float(frequencies[1 + int(np.argmax(magnitudes[1:]))])


def _oscillation_metrics(series: pd.Series, final_value: float) -> tuple[float, float]:
    residual = np.abs(series.to_numpy(dtype=float) - final_value)
    peaks = [
        index for index in range(1, len(residual) - 1)
        if residual[index] > residual[index - 1] and residual[index] >= residual[index + 1]
    ]
    peaks = [index for index in peaks if residual[index] > np.finfo(float).eps]
    if len(peaks) < 2:
        return 0.0, 0.0
    first, second = peaks[0], peaks[1]
    decrement = np.log(residual[first] / residual[second]) if residual[second] > 0 else 0.0
    damping = decrement / np.sqrt((2 * np.pi) ** 2 + decrement**2) if decrement > 0 else 0.0
    period = float(series.index[second] - series.index[first])
    decay_rate = decrement / period if period > 0 and decrement > 0 else 0.0
    halving = np.log(2) / decay_rate if decay_rate > 0 else 0.0
    return float(damping), float(halving)


def analyse_step(
    series: pd.Series,
    tmin: float = None,
    tmax: float = None,
    recovery_target_mw: Optional[float] = None,
    time_before_step: Optional[float] = None,
    select_first_recovery: Optional[bool] = True,
    series2: Optional[pd.Series] = None,
    commencement_thresholds: Optional[List[float]] = None,
) -> StepAnalysisResults:
    del time_before_step
    signal = _clean(series)
    if tmin is not None:
        signal = signal[signal.index >= tmin]
    if tmax is not None:
        signal = signal[signal.index <= tmax]
    signal = _clean(signal)

    start_time = float(signal.index[0])
    initial_value = float(signal.iloc[0])
    final_value = get_final_value(signal)
    min_value, max_value = float(signal.min()), float(signal.max())
    up_change, down_change = max_value - initial_value, min_value - initial_value
    direction = 1 if abs(up_change) >= abs(down_change) else -1
    largest_change = up_change if direction == 1 else down_change

    rise = rise_time(signal, initial_value, final_value, direction)
    settling = settle_time(signal, start_time, initial_value, final_value, largest_change)
    recovery = p_recovery_time(signal, start_time, recovery_target_mw, bool(select_first_recovery))
    if series2 is not None:
        trigger = _clean(series2).reindex(signal.index, method="nearest")
        commencement = commencement_time(
            signal, trigger, initial_value, final_value, direction, commencement_thresholds
        )
    else:
        commencement = CommencementTimeResults(rise.commencement_time_sec)
    damping, halving = _oscillation_metrics(signal, final_value)

    return StepAnalysisResults(
        start_time=start_time,
        initial_value=initial_value,
        final_value=final_value,
        min_value=min_value,
        max_value=max_value,
        largest_change=largest_change,
        largest_change_direction=direction,
        rise_time_results=rise,
        p_recovery_time_results=recovery,
        settling_time_results=settling,
        halving_time_sec=halving,
        damping_ratio=damping,
        CommencementTimeResults=commencement,
    )
