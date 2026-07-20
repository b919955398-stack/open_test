"""Replot previously completed PSS/E studies.

This replaces Pallet's ``Out`` wrapper with :mod:`hbess_open.io.psse_out` and
pairs result/spec files by stem instead of relying on directory-list order.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

from hbess_open.io.psse_out import out_to_df


def _spec_index(root: Path) -> Dict[str, dict]:
    running_spec = root / "running_spec.csv"
    if not running_spec.exists():
        return {}
    frame = pd.read_csv(running_spec)
    if "File_Name" not in frame.columns:
        return {}
    return {
        str(row["File_Name"]): {
            key: (None if pd.isna(value) else value) for key, value in row.to_dict().items()
        }
        for _, row in frame.iterrows()
    }


def _load_scenario(sim_path: Path, fallback: Dict[str, dict]) -> dict:
    json_path = sim_path.with_suffix(".json")
    if json_path.exists():
        with json_path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    try:
        return fallback[sim_path.stem]
    except KeyError as exc:
        raise FileNotFoundError(
            "Missing scenario metadata for {} (expected {} or running_spec.csv)".format(
                sim_path.name, json_path.name
            )
        ) from exc


def _simulation_paths(root: Path, extension: str) -> Iterable[Path]:
    suffix = extension.lower()
    for path in sorted(root.rglob("*" + suffix)):
        if path.is_file() and "_work" not in path.parts and "replots" not in path.parts:
            yield path


def replot_psse(
    extension: str,
    replotter: object,
    PLOT_INPUTS_DIR,
    PLOT_OUT_DIR,
    x86: bool = True,
    psse_config: Optional[dict] = None,
):
    """Regenerate PNG/PDF plots from OUT, CSV or pickle results.

    For ``.out`` inputs, an adjacent CSV is preferred. ``dyntools`` is only
    required for legacy OUT-only directories.
    """
    if not x86:
        raise NotImplementedError("replot_psse is the PSS/E replot entry point")
    extension = extension.lower()
    if extension not in {".out", ".csv", ".pkl", ".pickle"}:
        raise ValueError("Unsupported replot extension: {}".format(extension))

    input_root = Path(PLOT_INPUTS_DIR).resolve()
    output_root = Path(PLOT_OUT_DIR).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if not input_root.is_dir():
        raise FileNotFoundError("PLOT_INPUTS_DIR does not exist: {}".format(input_root))

    fallback = _spec_index(input_root)
    paths = list(_simulation_paths(input_root, extension))
    if not paths:
        print("No {} files found below {}".format(extension, input_root))
        return []

    results = []
    print("Replotting {} PSS/E studies ...".format(len(paths)))
    for index, sim_path in enumerate(paths, start=1):
        relative_parent = sim_path.parent.relative_to(input_root)
        case_output = output_root / relative_parent
        case_output.mkdir(parents=True, exist_ok=True)
        png_path = case_output / (sim_path.stem + ".png")
        pdf_path = case_output / (sim_path.stem + ".pdf")
        scenario = _load_scenario(sim_path, fallback)
        frame = out_to_df(sim_path, psse_config=psse_config)
        replotter.plot_from_df_and_dict(
            df=frame,
            scenario_dict=scenario,
            png_path=str(png_path),
            pdf_path=str(pdf_path),
        )
        results.append({"file_name": sim_path.stem, "png": str(png_path), "pdf": str(pdf_path)})
        print("[{}/{}] {}".format(index, len(paths), sim_path.stem))

    print("Finished replotting.")
    return results
