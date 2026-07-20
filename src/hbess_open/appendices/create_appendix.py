"""Create clause appendices from generated plots and SPEC metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from hbess_open.appendices.appendix_generation_heywoodbess import generate_appendix_heywoodbess
from hbess_open.open_psse.specs import load_specs_from_multiple_xlsx
from hbess_open.utils.remove_underscores import caption_preprocessor


def _metadata(frame: pd.DataFrame, psse_report: bool, fallback_title: str) -> tuple[str, int]:
    title_key = "Appendix_Name_PSSE" if psse_report else "Appendix_Name_PSCAD"
    report_key = "Report_No_PSSE" if psse_report else "Report_No_PSCAD"
    title = fallback_title
    report_number = 0
    if not frame.empty and title_key in frame.columns and pd.notna(frame.iloc[0].get(title_key)):
        title = str(frame.iloc[0][title_key])
    if not frame.empty and report_key in frame.columns and pd.notna(frame.iloc[0].get(report_key)):
        report_number = int(float(frame.iloc[0][report_key]))
    return title, report_number


def _document_number(number) -> str:
    return "HEYWOODBESS-GR-RPT-{:03d}".format(int(number))


def create_appendix_heywoodbess(
    PLOT_RESULTS_DIRS: Sequence[str],
    OUTPUT_DIR_DMAT: str,
    OUTPUT_DIR_CSR: str,
    XLSX_PATHS: Sequence[str],
    SHEETS_TO_PROCESS: Sequence[Sequence[str]],
    NOW_STR: str,
    issued_date: str,
    revision_no: str,
    x86: bool,
    overwrite_title: Optional[bool] = False,
    hard_title: Optional[str] = None,
    report_no: Optional[int] = None,
    create_discharge_appendices: bool = True,
    create_charge_appendices: bool = True,
):
    """Generate CSR combined and DMAT charge/discharge appendix PDFs."""
    spec = load_specs_from_multiple_xlsx(XLSX_PATHS, SHEETS_TO_PROCESS)
    if "Category" not in spec.columns:
        raise KeyError("The selected SPEC sheets do not contain a Category column")

    outputs = []
    print("Creating appendices ...")
    for plot_results_dir in PLOT_RESULTS_DIRS:
        plot_root = Path(plot_results_dir)
        if not plot_root.is_dir():
            raise FileNotFoundError("Plot results directory does not exist: {}".format(plot_root))

        for folder in sorted(path for path in plot_root.iterdir() if path.is_dir()):
            category_spec = spec[spec["Category"].astype(str) == folder.name].copy()
            if category_spec.empty:
                print("Skipping {}: Category is not present in the selected sheets".format(folder.name))
                continue

            title, number = _metadata(category_spec, x86, "Appendix {}".format(folder.name))
            if overwrite_title:
                title = hard_title or title
                if report_no is not None:
                    number = int(report_no)

            common = dict(
                project_name="Heywood BESS",
                client="Atmos",
                issued_date=issued_date,
                revision=revision_no,
                revision_history_csv_path="revisionhistory.csv",
                plots_directory=str(folder),
                caption_preprocessor_fn=caption_preprocessor,
            )

            if "CSR" in folder.name.upper():
                output = Path(OUTPUT_DIR_CSR) / "Appendix_{}".format(NOW_STR) / (title + ".pdf")
                outputs.append(
                    generate_appendix_heywoodbess(
                        title=title,
                        doc_number=_document_number(number),
                        output_path=str(output),
                        bess_charging=None,
                        **common,
                    )
                )
                continue

            charge_spec = category_spec[
                category_spec["File_Name"].astype(str).str.contains("CRG", case=False, na=False)
            ]
            discharge_spec = category_spec[
                ~category_spec["File_Name"].astype(str).str.contains("CRG", case=False, na=False)
            ]
            plot_names = [path.name.upper() for path in folder.rglob("*.png")]

            if create_charge_appendices and charge_spec.shape[0] and any("CRG" in name for name in plot_names):
                charge_title, charge_number = _metadata(charge_spec, x86, title)
                if overwrite_title:
                    charge_title = hard_title or charge_title
                    charge_number = int(report_no) if report_no is not None else charge_number
                output = Path(OUTPUT_DIR_DMAT) / "Charging Appendix" / NOW_STR / (charge_title + ".pdf")
                outputs.append(
                    generate_appendix_heywoodbess(
                        title=charge_title,
                        doc_number=_document_number(charge_number),
                        output_path=str(output),
                        bess_charging=True,
                        **common,
                    )
                )

            if create_discharge_appendices and discharge_spec.shape[0] and any("CRG" not in name for name in plot_names):
                discharge_title, discharge_number = _metadata(discharge_spec, x86, title)
                if overwrite_title:
                    discharge_title = hard_title or discharge_title
                    discharge_number = int(report_no) if report_no is not None else discharge_number
                output = Path(OUTPUT_DIR_DMAT) / "Discharging Appendix" / NOW_STR / (discharge_title + ".pdf")
                outputs.append(
                    generate_appendix_heywoodbess(
                        title=discharge_title,
                        doc_number=_document_number(discharge_number),
                        output_path=str(output),
                        bess_charging=False,
                        **common,
                    )
                )

    print("Finished appendix generation ({} PDFs).".format(len(outputs)))
    return outputs
