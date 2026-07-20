import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from hbess_open.studyrunners.psse_study_runner import run_psse_studies


class _Config:
    def __init__(self):
        self.data = {"dynamics": {}}


class _ImmediateEngine:
    plotted_before_next_case = []

    def __init__(self, config):
        self.output_dir = Path(config.data["output_dir"])

    def run(self, plans, result_callback=None):
        results = []
        plans = list(plans)
        for number, plan in enumerate(plans, start=1):
            name = plan.scenario.file_name
            category = plan.scenario.category
            result_dir = self.output_dir / category
            result_dir.mkdir(parents=True, exist_ok=True)
            if number > 1:
                previous = plans[number - 2].scenario
                previous_dir = self.output_dir / previous.category
                self.plotted_before_next_case.append((previous_dir / (previous.file_name + ".png")).exists())
            out_path = result_dir / (name + ".out")
            csv_path = result_dir / (name + ".csv")
            out_path.write_bytes(b"out")
            pd.DataFrame({"time": [0.0], "P": [1.0]}).to_csv(csv_path, index=False)
            result = {"file_name": name, "status": "completed", "out": str(out_path), "csv": str(csv_path)}
            results.append(result)
            result_callback(result, plan, number, len(plans))
        return results


class _FilePlotter:
    def plot_from_df_and_dict(self, df, scenario_dict, png_path, pdf_path):
        Path(png_path).write_bytes(b"png")
        Path(pdf_path).write_bytes(b"pdf")


class StudyRunnerOutputTests(unittest.TestCase):
    def test_each_case_is_plotted_immediately_and_temporary_csv_is_removed(self):
        spec = pd.DataFrame([
            {"File_Name": "case_1", "Category": "CSR", "PSSE": True, "Grid_SCR": 3.0,
             "Grid_X2R_sig": 5.0, "Grid_FL_MVA_sig": 900.0, "Post_Init_Duration_s": 1.0},
            {"File_Name": "case_2", "Category": "CSR", "PSSE": True, "Grid_SCR": 3.0,
             "Grid_X2R_sig": 5.0, "Grid_FL_MVA_sig": 900.0, "Post_Init_Duration_s": 1.0},
        ])
        _ImmediateEngine.plotted_before_next_case = []
        with tempfile.TemporaryDirectory() as results_dir, \
                patch("hbess_open.studyrunners.psse_study_runner._load_config", return_value=_Config()), \
                patch("hbess_open.studyrunners.psse_study_runner.StudyEngine", _ImmediateEngine), \
                patch("hbess_open.studyrunners.psse_study_runner.build_plan", side_effect=lambda scenario: SimpleNamespace(scenario=scenario)):
            results = run_psse_studies(
                spec, _FilePlotter(), "model", results_dir,
                plot_results=True, keep_csv_results=False,
                save_run_manifests=False, verbose=False,
            )
            category = Path(results_dir) / "CSR"
            self.assertEqual(_ImmediateEngine.plotted_before_next_case, [True])
            self.assertTrue((category / "case_1.png").exists())
            self.assertTrue((category / "case_1.pdf").exists())
            self.assertFalse((category / "case_1.csv").exists())
            self.assertNotIn("csv", results[0])
            self.assertFalse((Path(results_dir) / "running_spec.csv").exists())
            self.assertFalse((Path(results_dir) / "study_plan.json").exists())


if __name__ == "__main__":
    unittest.main()
