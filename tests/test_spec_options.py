import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from hbess_open.open_psse.specs import load_spec_options


class SpecOptionTests(unittest.TestCase):
    def make_workbook(self, directory):
        path = Path(directory) / "spec.xlsx"
        wb = Workbook()
        wb.active.title = "Revision History"
        for sheet, rows in {
            "5255_Faults": [
                ["File_Name", "PSSE", "Test No", "Test Category"],
                ["fault_1", "yes", 1, "BalFault"],
                ["fault_2", "no", 2, "BalFault"],
            ],
            "52511_Fgrid": [
                ["File_Name", "PSSE", "Test No", "Test Category"],
                ["fgrid_1", 1, 11, "Fgrid"],
            ],
            "5255_Faults_OLD": [
                ["File_Name", "PSSE", "Test No", "Test Category"],
                ["old_1", True, 99, "BalFault"],
            ],
        }.items():
            ws = wb.create_sheet(sheet)
            for row in rows:
                ws.append(row)
        wb.save(path)
        return path

    def test_globs_exclusions_enabled_and_filters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_workbook(directory)
            result = load_spec_options({
                "sources": [
                    {"name": "ignored", "path": "missing.xlsx", "sheets": [], "enabled": True},
                    {"name": "CSR", "path": path, "sheets": ["5255_*", "!5255_*_OLD", "52511_*"]},
                ],
                "enabled_only": True,
                "filters": {"Test No": [1, 11]},
                "include_file_names": ["fault_*", "fgrid_*"],
                "duplicate_policy": "error",
            })
            self.assertEqual(result["File_Name"].tolist(), ["fault_1", "fgrid_1"])
            self.assertEqual(result["Spec_Source"].tolist(), ["CSR", "CSR"])
            self.assertEqual(result["Spec_Row"].tolist(), [2, 2])

    def test_missing_sheet_suggests_nearest_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_workbook(directory)
            with self.assertRaisesRegex(ValueError, "closest: 52511_Fgrid"):
                load_spec_options({
                    "sources": [{"path": path, "sheets": ["52511_Fgrd"]}],
                    "enabled_only": False,
                })

    def test_comparison_operators(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_workbook(directory)
            result = load_spec_options({
                "sources": [{"path": path, "sheets": ["5255_Faults", "52511_Fgrid"]}],
                "enabled_only": False,
                "filters": {"Test No": {">=": 2, "<=": 11}},
                "duplicate_policy": "allow",
            })
            self.assertEqual(result["File_Name"].tolist(), ["fault_2", "fgrid_1"])

            result = load_spec_options({
                "sources": [{"path": path, "sheets": ["5255_Faults"]}],
                "enabled_only": False,
                "filters": {"Test No": "== 2"},
                "duplicate_policy": "allow",
            })
            self.assertEqual(result["File_Name"].tolist(), ["fault_2"])

    def test_duplicate_file_names_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_workbook(directory)
            with self.assertRaisesRegex(ValueError, "Duplicate SPEC File_Name"):
                load_spec_options({
                    "sources": [{"path": path, "sheets": ["5255_*", "52511_Fgrid"]}],
                    "enabled_only": True,
                    "duplicate_policy": "error",
                    "filename_column": "Test Category",
                })


if __name__ == "__main__":
    unittest.main()
