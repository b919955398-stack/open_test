import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from psse_open.commands import build_plan
from psse_open.config import ProjectConfig
from psse_open.engine import RESULT_METADATA_KEY, StudyEngine
from psse_open.models import PlaybackPoint, Scenario, StudyPlan


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
        return {}

    def apply_event(self, event, scenario):
        pass

    def run_to(self, time_s):
        pass

    def halt(self):
        pass


class _PlaybackBackend(_Backend):
    def __init__(self, order):
        super().__init__(order)
        self.generated_plb_paths = []

    @staticmethod
    def playback_text(playback):
        lines = [
            "{:.9g} {:.9g} {:.9g}".format(
                point.time, point.voltage_pu, point.frequency_hz
            )
            for point in playback
        ]
        last = playback[-1]
        lines.append(
            "99999 {:.9g} {:.9g}".format(
                last.voltage_pu, last.frequency_hz
            )
        )
        return "\n".join(lines) + "\n"

    def initialize_dynamics(
        self, work_dir, dyr_path, out_path, playback, initialised_sav_path=None
    ):
        super().initialize_dynamics(
            work_dir,
            dyr_path,
            out_path,
            playback,
            initialised_sav_path=initialised_sav_path,
        )
        if not playback:
            return {}
        plb_path = Path(work_dir) / (
            "generated_{}.plb".format(Path(out_path).stem)
        )
        plb_path.write_text(self.playback_text(playback), encoding="ascii")
        self.generated_plb_paths.append(plb_path)
        voltages = [point.voltage_pu for point in playback]
        frequencies = [point.frequency_hz for point in playback]
        return {
            "stem": plb_path.stem,
            "plb_path": str(plb_path),
            "dyr_path": str(Path(work_dir) / (plb_path.stem + ".dyr")),
            "points": len(playback),
            "voltage_min_pu": min(voltages),
            "voltage_max_pu": max(voltages),
            "voltage_span_pu": max(voltages) - min(voltages),
            "frequency_min_hz": min(frequencies),
            "frequency_max_hz": max(frequencies),
        }


class _TovOrderBackend(_Backend):
    def ensure_tov_fixed_shunt(self):
        self.order.append("ensure_tov_fixed_shunt")

    def initialize_dynamics(
        self, work_dir, dyr_path, out_path, playback, initialised_sav_path=None
    ):
        self.order.append("initialize_dynamics")
        return super().initialize_dynamics(
            work_dir,
            dyr_path,
            out_path,
            playback,
            initialised_sav_path=initialised_sav_path,
        )


class EngineRuntimeTests(unittest.TestCase):
    @staticmethod
    def _make_engine(root, backend):
        model = root / "model"
        output = root / "output"
        model.mkdir(exist_ok=True)
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
            "resume_require_plots": False,
            "files": {"sav": "base.sav", "dyr": "base.dyr", "copy_globs": []},
            "system": {
                "poc_bus": 1,
                "infinite_bus": 2,
                "grid_branch": {"from_bus": 1, "to_bus": 2, "id": "1"},
                "infinite_machine": {"id": "1"},
            },
            "dynamics": {"frequency_hz": 50.0},
        })
        engine = StudyEngine.__new__(StudyEngine)
        engine.config = config
        engine.psspy = object()
        engine.dyntools = object()
        engine.hooks = None
        engine.backend = backend
        return engine, output

    @staticmethod
    def _fake_out_to_csv(out_path, csv_path, dyntools, nominal_frequency_hz):
        Path(csv_path).write_text("time,P\n0,0\n", encoding="utf-8")

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

    def test_tov_placeholder_is_ensured_before_dynamic_initialization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            order = []
            backend = _TovOrderBackend(order)
            engine, _output = self._make_engine(root, backend)
            engine.config.data["system"]["fixed_shunts"] = {
                "tov": {"bus": 331184, "id": "1"}
            }
            scenario = Scenario("5255_TOV", 2, "fixed_shunt_tov", True, {
                "File_Name": "fixed_shunt_tov",
                "Category": "5255_TOV",
                "Post_Init_Duration_s": 1.0,
                "PSSE Commands": (
                    "CHANGE FIXED_SHUNT 'tov' MVAR TO 1109.709 AT 0.5s; "
                    "TRIP FIXED_SHUNT 'tov' AT 0.93s"
                ),
            })

            with patch(
                "psse_open.engine.out_to_csv", side_effect=self._fake_out_to_csv
            ):
                result = engine.run([build_plan(scenario)])[0]

            self.assertEqual(result["status"], "completed")
            self.assertLess(
                order.index("start:fixed_shunt_tov"),
                order.index("ensure_tov_fixed_shunt"),
            )
            self.assertLess(
                order.index("ensure_tov_fixed_shunt"),
                order.index("initialize_dynamics"),
            )

    def test_structured_tov_uses_the_same_pre_init_placeholder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            order = []
            backend = _TovOrderBackend(order)
            engine, _output = self._make_engine(root, backend)
            engine.config.data["system"]["fixed_shunts"] = {
                "tov": {"bus": 331184, "id": "1"}
            }
            scenario = Scenario("5255_TOV", 2, "structured_tov", True, {
                "File_Name": "structured_tov",
                "Category": "5255_TOV",
                "Post_Init_Duration_s": 1.0,
                "TOV_MVAr": 1109.709,
                "Fault_Time": 0.5,
                "Fault_Duration": 0.43,
            })

            with patch(
                "psse_open.engine.out_to_csv", side_effect=self._fake_out_to_csv
            ):
                result = engine.run([build_plan(scenario)])[0]

            self.assertEqual(result["status"], "completed")
            self.assertLess(
                order.index("ensure_tov_fixed_shunt"),
                order.index("initialize_dynamics"),
            )

    def test_vgrid_fgrid_playback_is_retained_with_scenario_name_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = _PlaybackBackend([])
            engine, output = self._make_engine(root, backend)
            scenario = Scenario("5255_Vgrid_Fgrid", 2, "vgrid_fgrid_case", True, {
                "File_Name": "vgrid_fgrid_case",
                "Category": "5255_Vgrid_Fgrid",
                "Post_Init_Duration_s": 0,
                "Vslack_pu_psse": "1, AT 0.5s ↑ 1.1",
                "Fslack_Hz_sig": "50, AT 0.75s ↑ 51",
            })
            plan = build_plan(scenario)
            self.assertTrue(plan.playback)

            with patch(
                "psse_open.engine.out_to_csv", side_effect=self._fake_out_to_csv
            ):
                result = engine.run([plan])[0]

            retained = output / "5255_Vgrid_Fgrid" / "vgrid_fgrid_case.plb"
            self.assertEqual(retained.read_text(encoding="ascii"), backend.playback_text(plan.playback))
            self.assertEqual(result["plb"], str(retained))
            self.assertEqual(result["playback"]["result_path"], str(retained))
            self.assertFalse(backend.generated_plb_paths[0].exists())

            case_metadata = json.loads(
                (retained.parent / "vgrid_fgrid_case.json").read_text(encoding="utf-8")
            )[RESULT_METADATA_KEY]
            self.assertEqual(case_metadata["plb_path"], str(retained))
            status = json.loads((output / "run_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status[0]["plb"], str(retained))

    def test_scenario_without_playback_does_not_retain_a_plb(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = _PlaybackBackend([])
            engine, output = self._make_engine(root, backend)
            result_dir = output / "CSR"
            result_dir.mkdir(parents=True)
            stale_plb = result_dir / "no_playback.plb"
            stale_plb.write_bytes(b"stale playback")
            plan = StudyPlan(
                Scenario("CSR", 2, "no_playback", True, {
                    "File_Name": "no_playback",
                    "Category": "CSR",
                    "Post_Init_Duration_s": 0,
                }),
                [],
            )

            with patch(
                "psse_open.engine.out_to_csv", side_effect=self._fake_out_to_csv
            ):
                result = engine.run([plan])[0]

            self.assertFalse(stale_plb.exists())
            self.assertNotIn("plb", result)
            self.assertEqual(backend.generated_plb_paths, [])
            status = json.loads((output / "run_status.json").read_text(encoding="utf-8"))
            self.assertNotIn("plb", status[0])

    def test_changed_playback_profile_rewrites_plb_and_invalidates_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = _PlaybackBackend([])
            engine, output = self._make_engine(root, backend)
            scenario = Scenario("5255_Vgrid_Fgrid", 2, "profile_change", True, {
                "File_Name": "profile_change",
                "Category": "5255_Vgrid_Fgrid",
                "Post_Init_Duration_s": 0,
            })
            first_plan = StudyPlan(scenario, [], [
                PlaybackPoint(0.0, 1.0, 50.0),
                PlaybackPoint(1.0, 1.1, 50.5),
            ])
            second_plan = StudyPlan(scenario, [], [
                PlaybackPoint(0.0, 1.0, 50.0),
                PlaybackPoint(1.0, 0.9, 49.5),
            ])
            retained = output / "5255_Vgrid_Fgrid" / "profile_change.plb"

            with patch(
                "psse_open.engine.out_to_csv", side_effect=self._fake_out_to_csv
            ):
                first = engine.run([first_plan])[0]
                first_contents = retained.read_text(encoding="ascii")
                second = engine.run([second_plan])[0]
                second_contents = retained.read_text(encoding="ascii")
                resumed = engine.run([second_plan])[0]
                retained.unlink()
                missing_plb_rerun = engine.run([second_plan])[0]

            self.assertEqual(first_contents, backend.playback_text(first_plan.playback))
            self.assertEqual(second_contents, backend.playback_text(second_plan.playback))
            self.assertNotEqual(first_contents, second_contents)
            self.assertNotEqual(first["result_fingerprint"], second["result_fingerprint"])
            self.assertEqual(second["resume_status"], "miss")
            self.assertEqual(resumed["resume_status"], "hit")
            self.assertEqual(resumed["plb"], str(retained))
            self.assertEqual(missing_plb_rerun["resume_status"], "miss")
            self.assertEqual(retained.read_text(encoding="ascii"), second_contents)
            self.assertEqual(len(backend.generated_plb_paths), 3)


if __name__ == "__main__":
    unittest.main()
