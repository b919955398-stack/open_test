"""SPEC-to-report-table conversion without Pallet."""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

import pandas as pd

from hbess_open.open_psse.specs import load_specs_from_multiple_xlsx, load_specs_from_xlsx


def _add_fault_impedance(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["Fault_Impedance"] = None
    for index, row in result.iterrows():
        ures = row.get("Ures_sig")
        z_ratio = row.get("Zf2Zs_sig")
        r_offset = row.get("Rf_Offset_sig")
        if pd.notna(ures):
            result.at[index, "Fault_Impedance"] = "{} pu".format(ures)
        elif pd.notna(z_ratio):
            if pd.notna(r_offset) and float(r_offset) > 0:
                result.at[index, "Fault_Impedance"] = "{} Ω".format(r_offset)
            else:
                result.at[index, "Fault_Impedance"] = "Zf = {} Zs".format(z_ratio)
    return result


def _normalise_numeric_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        converted = pd.to_numeric(result[column], errors="coerce")
        non_blank = result[column].notna()
        if non_blank.any() and converted[non_blank].notna().all():
            result[column] = converted
    return result


def _mapped_sheet(spec: pd.DataFrame, mapping: pd.Series, x86: bool) -> tuple[str, pd.DataFrame]:
    mapping = mapping[mapping.notna()].copy()
    if "Sheet_To_Update" not in mapping.index:
        raise ValueError("Column mapping row is missing Sheet_To_Update")
    sheet_name = str(mapping.pop("Sheet_To_Update"))

    # A PSS/E report does not include the PSCAD appendix field, and vice versa.
    drop_key = "Appendix_Name_PSCAD" if x86 else "Appendix_Name_PSSE"
    if drop_key in mapping.index:
        mapping = mapping.drop(labels=[drop_key])

    sheet = spec[spec["Sheet_Name"].astype(str) == sheet_name].copy()
    if sheet.empty:
        return sheet_name, sheet
    missing = [str(name) for name in mapping.index if str(name) not in sheet.columns]
    for column in missing:
        if column == "Readable_Name" and "File_Name" in sheet.columns:
            sheet[column] = sheet["File_Name"]
        else:
            sheet[column] = None
    if missing:
        print("{}: blank/default values used for missing columns {}".format(sheet_name, ", ".join(missing)))

    source_columns = [str(value) for value in mapping.index]
    output_columns = [str(value) for value in mapping.values]
    sheet = sheet[source_columns].copy()
    sheet.columns = output_columns
    return sheet_name, _normalise_numeric_columns(sheet)


def _write_sheet_tables(sheet_name: str, frame: pd.DataFrame, output_dir: Path) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    filename = sheet_name.replace("_", "-")
    if sheet_name in {"324_325_Faults", "324_325_Faults_CRG"} and "Type" in frame.columns:
        groups = {
            "balanced": frame[frame["Type"] == "3PHG"],
            "unbalanced": frame[frame["Type"] != "3PHG"],
        }
        for label, group in groups.items():
            path = output_dir / "{}-{}-test-table.csv".format(filename, label)
            group.to_csv(path, index=False, float_format="%g")
            paths.append(path)
    else:
        path = output_dir / "{}-test-table.csv".format(filename)
        frame.to_csv(path, index=False, float_format="%g")
        paths.append(path)
    return paths


def create_report_table_CSR_DMAT(
    COLMAP_PATHS: Sequence[str],
    SPEC_PATHS: Sequence[str],
    SHEETS_TO_PROCESS: Sequence[Sequence[str]],
    OUTPUT_DIRS: Sequence[str],
    x86: bool,
):
    """Create all mapped CSR/DMAT CSV tables selected by the master script."""
    if len(COLMAP_PATHS) != len(OUTPUT_DIRS):
        raise ValueError("COLMAP_PATHS and OUTPUT_DIRS must have matching lengths")
    spec = load_specs_from_multiple_xlsx(SPEC_PATHS, SHEETS_TO_PROCESS)
    spec = _add_fault_impedance(spec)
    written: List[Path] = []

    print("Creating report tables ...")
    for map_path, output_dir in zip(COLMAP_PATHS, OUTPUT_DIRS):
        mapping_frame = pd.read_csv(map_path)
        for _, mapping in mapping_frame.iterrows():
            sheet_name, table = _mapped_sheet(spec, mapping, x86=x86)
            if table.empty:
                print("Skipping {}: sheet was not selected or contains no rows".format(sheet_name))
                continue
            written.extend(_write_sheet_tables(sheet_name, table, Path(output_dir)))
    print("Finished table generation ({} files).".format(len(written)))
    return [str(path) for path in written]


def create_report_table(COLMAP_PATH, SPEC_PATH, SHEETS_TO_PROCESS, OUTPUT_DIR):
    """Single-workbook compatibility entry point from the supplied utility."""
    spec = _add_fault_impedance(load_specs_from_xlsx(SPEC_PATH, SHEETS_TO_PROCESS))
    written: List[Path] = []
    for _, mapping in pd.read_csv(COLMAP_PATH).iterrows():
        sheet_name, table = _mapped_sheet(spec, mapping, x86=True)
        if not table.empty and sheet_name in SHEETS_TO_PROCESS:
            written.extend(_write_sheet_tables(sheet_name, table, Path(OUTPUT_DIR)))
    return [str(path) for path in written]
