import tempfile
import json
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


class _FlatTovEngine:
    def __init__(self, config):
        self.output_dir = Path(config.data["output_dir"])

    def run(self, plans, result_callback=None):
        plan = list(plans)[0]
        name = plan.scenario.file_name
        result_dir = self.output_dir / plan.scenario.category
        result_dir.mkdir(parents=True, exist_ok=True)
        out_path = result_dir / (name + ".out")
        csv_path = result_dir / (name + ".csv")
        out_path.write_bytes(b"out")
        pd.DataFrame({
            "time": [0.0, 0.5, 0.93],
            "V_POC_PU": [1.0, 1.0, 1.0],
        }).to_csv(csv_path, index=False)
        # These represent old plots from an earlier fingerprint and must not
        # survive a newly detected invalid TOV result.
        (result_dir / (name + ".png")).write_bytes(b"stale png")
        (result_dir / (name + ".pdf")).write_bytes(b"stale pdf")
        result = {
            "file_name": name,
            "status": "completed",
            "out": str(out_path),
            "csv": str(csv_path),
        }
        result_callback(result, plan, 1, 1)
        return [result]


class StudyRunnerOutputTests(unittest.TestCase):
    def test_each_case_is_eventually_plotted_and_temporary_csv_is_removed(self):
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
            self.assertEqual(len(_ImmediateEngine.plotted_before_next_case), 1)
            self.assertTrue((category / "case_1.png").exists())
            self.assertTrue((category / "case_1.pdf").exists())
            self.assertFalse((category / "case_1.csv").exists())
            self.assertNotIn("csv", results[0])
            self.assertEqual(results[0]["plot_status"], "completed")
            self.assertFalse((Path(results_dir) / "running_spec.csv").exists())
            self.assertFalse((Path(results_dir) / "study_plan.json").exists())

    def test_flat_tov_preserves_diagnostic_csv_and_removes_stale_plots(self):
        spec = pd.DataFrame([{
            "File_Name": "flat_tov",
            "Category": "329_TOV",
            "PSSE": True,
            "Grid_SCR": 3.0,
            "Grid_X2R_sig": 5.0,
            "Grid_FL_MVA_sig": 900.0,
            "U_Ov": 1.2,
            "Post_Init_Duration_s": 1.0,
        }])
        with tempfile.TemporaryDirectory() as results_dir, \
                patch("hbess_open.studyrunners.psse_study_runner._load_config", return_value=_Config()), \
                patch("hbess_open.studyrunners.psse_study_runner.StudyEngine", _FlatTovEngine), \
                patch(
                    "hbess_open.studyrunners.psse_study_runner.build_plan",
                    side_effect=lambda scenario: SimpleNamespace(
                        scenario=scenario, events=[], playback=[]
                    ),
                ):
            with self.assertRaisesRegex(RuntimeError, "flat/invalid"):
                run_psse_studies(
                    spec,
                    _FilePlotter(),
                    "model",
                    results_dir,
                    plot_in_background=False,
                    verbose=False,
                )
            category = Path(results_dir) / "329_TOV"
            self.assertTrue((category / "flat_tov.csv").is_file())
            self.assertFalse((category / "flat_tov.png").exists())
            self.assertFalse((category / "flat_tov.pdf").exists())
            status = json.loads((Path(results_dir) / "run_status.json").read_text())
            self.assertEqual(status[0]["validation_status"], "failed")
            self.assertEqual(status[0]["plot_status"], "skipped_invalid_tov")


if __name__ == "__main__":
    unittest.main()
