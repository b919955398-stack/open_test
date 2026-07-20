from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Dict

import pandas as pd


def invoke_project_plotter(plotter: object, csv_path: str, scenario: Dict[str, Any], results_dir: str) -> bool:
    """Call common Grid-Link plotter signatures without depending on Pallet."""
    if plotter is None:
        return False
    method = getattr(plotter, "plot_from_df_and_dict", None)
    if method is None:
        return False
    dataframe = pd.read_csv(csv_path)
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
            "Check the active .chandef and the CSV header.".format(missing, csv_path)
        ) from exc
    missing_outputs = [path for path in (png_path, pdf_path) if not Path(path).is_file()]
    if missing_outputs:
        raise RuntimeError("Plotter returned without creating: {}".format(", ".join(missing_outputs)))
    return True
