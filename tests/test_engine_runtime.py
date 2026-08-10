import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from psse_open.config import ProjectConfig
from psse_open.engine import StudyEngine
from psse_open.models import Scenario, StudyPlan


class _Backend:
    def __init__(self, order):
        self.order = order

    def initialize(self, sav_path, log_stem):
        self.order.append("start:" + Path(log_stem).name)

    def configure_scenario_options(self, scenario):
        pass

    def configure_grid(self, scenario):
        return 0.0, 0.1

    def dispatch(self, scenario, r_pu, x_pu):
        pass

    def make_grid_infinite(self):
        pass

    def initialize_dynamics(
        self, work_dir, dyr_path, out_path, playback, initialised_sav_path=None
    ):
        if initialised_sav_path is not None:
            Path(initialised_sav_path).write_bytes(b"initialised sav")
        Path(out_path).write_bytes(b"out")

    def apply_event(self, event, scenario):
        pass

    def run_to(self, time_s):
        pass

    def halt(self):
        pass


class EngineRuntimeTests(unittest.TestCase):
    def test_inputs_are_staged_once_and_callback_precedes_next_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model"
            output = root / "output"
            model.mkdir()
            (model / "base.sav").write_bytes(b"sav")
            (model / "base.dyr").write_bytes(b"dyr")
            config = ProjectConfig(str(model / "config.json"), {
                "project_root": str(model),
                "output_dir": str(output),
                "result_layout": "pallet",
                "continue_on_error": True,
                "keep_runtime_files": False,
                "keep_scenario_json": True,
                "resume_completed_results": True,
                "resume_require_plots": True,
                "files": {"sav": "base.sav", "dyr": "base.dyr", "copy_globs": []},
                "system": {"poc_bus": 1, "infinite_bus": 2, "grid_branch": {"from_bus": 1, "to_bus": 2, "id": "1"}, "infinite_machine": {"id": "1"}},
                "dynamics": {"frequency_hz": 50.0},
            })
            order = []
            engine = StudyEngine.__new__(StudyEngine)
            engine.config = config
            engine.psspy = object()
            engine.dyntools = object()
            engine.hooks = None
            engine.backend = _Backend(order)
            plans = [
                StudyPlan(Scenario("Sheet", i + 2, "case_{}".format(i + 1), True, {
                    "File_Name": "case_{}".format(i + 1), "Category": "CSR", "Post_Init_Duration_s": 0,
                }), [])
                for i in range(2)
            ]

            def fake_out_to_csv(out_path, csv_path, dyntools, nominal_frequency_hz):
                Path(csv_path).write_text("time,P\n0,0\n", encoding="utf-8")

            def callback(result, plan, number, total):
                order.append("callback:" + result["file_name"])
                if result.get("resume_status") == "hit":
                    result["plot_status"] = "reused"
                    return
                result_dir = Path(result["out"]).parent
                png_path = result_dir / (result["file_name"] + ".png")
                pdf_path = result_dir / (result["file_name"] + ".pdf")
                png_path.write_bytes(b"png")
                pdf_path.write_bytes(b"pdf")
                result.update(
                    plot_status="completed",
                    png=str(png_path),
                    pdf=str(pdf_path),
                )

            with patch("psse_open.engine.out_to_csv", side_effect=fake_out_to_csv), \
                    patch.object(engine, "_copy_inputs", wraps=engine._copy_inputs) as stage:
                results = engine.run(plans, result_callback=callback)

            self.assertEqual(stage.call_count, 1)
            self.assertEqual(order, [
                "start:case_1", "callback:case_1",
                "start:case_2", "callback:case_2",
            ])
            self.assertEqual([item["plot_status"] for item in results], ["completed", "completed"])
            for case_name in ("case_1", "case_2"):
                case_dir = output / "CSR"
                self.assertTrue((case_dir / (case_name + ".json")).is_file())
                self.assertEqual((case_dir / (case_name + ".out")).read_bytes(), b"out")
                self.assertEqual((case_dir / (case_name + ".dyr")).read_bytes(), b"dyr")
                self.assertEqual((case_dir / (case_name + ".png")).read_bytes(), b"png")
                self.assertEqual((case_dir / (case_name + ".pdf")).read_bytes(), b"pdf")
                self.assertEqual(
                    (case_dir / (case_name + "_initialised.sav")).read_bytes(),
                    b"initialised sav",
                )
            self.assertFalse((output / "_work").exists())
            self.assertFalse((output / "_runtime").exists())

            first_run_order = list(order)
            with patch("psse_open.engine.out_to_csv") as convert_again:
                resumed = engine.run(plans, result_callback=callback)
            self.assertEqual(
                order[len(first_run_order):],
                ["callback:case_1", "callback:case_2"],
            )
            convert_again.assert_not_called()
            self.assertEqual(
                [item["resume_status"] for item in resumed], ["hit", "hit"]
            )
            self.assertEqual(
                [item["plot_status"] for item in resumed], ["reused", "reused"]
            )


if __name__ == "__main__":
    unittest.main()
