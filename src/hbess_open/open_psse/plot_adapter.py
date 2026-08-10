from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd


def downsample_dataframe_for_plot(
    dataframe: pd.DataFrame,
    max_points: int = 20000,
    event_times=None,
) -> pd.DataFrame:
    """Reduce only the plotted copy while preserving disturbance boundaries.

    OUT data remains at full resolution.  Uniformly distributed samples keep
    the rendered line density bounded, and the nearest samples immediately
    around every compiled event/playback transition are always retained.
    """
    limit = int(max_points or 0)
    if limit <= 0 or len(dataframe) <= limit:
        return dataframe
    if "time" in dataframe.columns:
        times = pd.to_numeric(dataframe["time"], errors="coerce").to_numpy()
    else:
        times = np.asarray(
            pd.to_numeric(pd.Index(dataframe.index), errors="coerce"),
            dtype=float,
        )
    base = np.linspace(0, len(dataframe) - 1, num=limit, dtype=int)
    selected = set(int(index) for index in base)
    for event_time in event_times or []:
        if not np.isfinite(float(event_time)) or not np.isfinite(times).any():
            continue
        nearest = int(np.nanargmin(np.abs(times - float(event_time))))
        for offset in (-2, -1, 0, 1, 2):
            index = nearest + offset
            if 0 <= index < len(dataframe):
                selected.add(index)
    result = dataframe.iloc[sorted(selected)].copy()
    result.attrs["source_points"] = len(dataframe)
    result.attrs["plot_points"] = len(result)
    return result


def invoke_project_plotter_from_dataframe(
    plotter: object,
    dataframe: pd.DataFrame,
    scenario: Dict[str, Any],
    results_dir: str,
    source_description: str = "in-memory PSS/E OUT data",
) -> bool:
    """Call common Grid-Link plotter signatures with already-decoded data."""
    if plotter is None:
        return False
    method = getattr(plotter, "plot_from_df_and_dict", None)
    if method is None:
        return False
    dataframe = dataframe.copy(deep=False)
    if "time" in dataframe.columns:
        dataframe = dataframe.set_index("time")
    signature = inspect.signature(method)
    stem = str(scenario.get("File_Name", "plot"))
    png_path = str(Path(results_dir) / (stem + ".png"))
    pdf_path = str(Path(results_dir) / (stem + ".pdf"))
    Path(results_dir).mkdir(parents=True, exist_ok=True)
    values = {
        "df": dataframe,
        "dataframe": dataframe,
        "scenario": scenario,
        "spec": scenario,
        "spec_dict": scenario,
        "scenario_dict": scenario,
        "output_dir": results_dir,
        "results_dir": results_dir,
        "result_dir": results_dir,
        "output_path": png_path,
        "png_path": png_path,
        "pdf_path": pdf_path,
        "file_name": stem,
        "filename": stem,
    }
    kwargs = {}
    unresolved = []
    for name, parameter in signature.parameters.items():
        if name == "self":
            continue
        if name in values:
            kwargs[name] = values[name]
        elif parameter.default is inspect.Parameter.empty and parameter.kind not in (
            inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD
        ):
            unresolved.append(name)
    if unresolved:
        raise TypeError(
            "Cannot call plotter.plot_from_df_and_dict; upload the plotter or map required parameters: {}".format(", ".join(unresolved))
        )
    try:
        method(**kwargs)
    except KeyError as exc:
        missing = str(exc).strip("'\"")
        raise RuntimeError(
            "Plotter needs channel {!r}, but it is absent from {}. "
            "Check the active .chandef and decoded OUT channels.".format(
                missing, source_description
            )
        ) from exc
    missing_outputs = [path for path in (png_path, pdf_path) if not Path(path).is_file()]
    if missing_outputs:
        raise RuntimeError("Plotter returned without creating: {}".format(", ".join(missing_outputs)))
    return True


def invoke_project_plotter(plotter: object, csv_path: str, scenario: Dict[str, Any], results_dir: str) -> bool:
    """CSV compatibility wrapper used by replotting and older callers."""
    dataframe = pd.read_csv(csv_path)
    return invoke_project_plotter_from_dataframe(
        plotter,
        dataframe,
        scenario,
        results_dir,
        source_description=csv_path,
    )
