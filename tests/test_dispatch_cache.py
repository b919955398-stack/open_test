import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from psse_open.config import ProjectConfig
from psse_open.dispatch import DispatchCache, create_dispatch_plan
from psse_open.engine import StudyEngine
from psse_open.models import Event, Scenario, StudyPlan
from psse_open.progress import ConsoleReporter


def _config(root: Path, cache: Path) -> ProjectConfig:
    model = root / "model"
    output = root / "output"
    model.mkdir(exist_ok=True)
    (model / "base.sav").write_bytes(b"base sav v1")
    (model / "base.dyr").write_bytes(b"dyr")
    return ProjectConfig(str(model / "config.json"), {
        "project_root": str(model),
        "output_dir": str(output),
        "result_layout": "pallet",
        "continue_on_error": True,
        "keep_runtime_files": False,
        "keep_scenario_json": True,
        "files": {"sav": "base.sav", "dyr": "base.dyr", "copy_globs": []},
        "definition_files": {},
        "psse": {"version": 34, "max_buses": 1000},
        "bases": {"p_mw": 285.0, "q_mvar": 112.575, "normal_v_pu": 1.06},
        "system": {
            "poc_bus": 1,
            "infinite_bus": 2,
            "grid_branch": {"from_bus": 1, "to_bus": 2, "id": "1"},
            "infinite_machine": {"id": "1"},
        },
        "load_flow": {},
        "initialization": {},
        "dynamics": {"frequency_hz": 50.0},
        "dispatch_cache": {
            "enabled": True,
            "directory": str(cache),
            "rebuild": False,
            "key_columns": [],
            "automatic_key_columns": True,
            "verify_hashes": False,
        },
        "progress": {"level": "quiet", "print_case_spec": False, "spec_fields": []},
    })


def _plan(name: str, inverter_count=100, temperature=25.0, tap_ratio=1.0, event_time=5.0) -> StudyPlan:
    values = {
        "File_Name": name,
        "Category": "MFRT",
        "PSSE": True,
        "Ppoc_MW_sig": 285.0,
        "Qpoc_MVAr_init": 0.0,
        "Vpoc_pu_sig": 1.06,
        "Grid_SCR": 3.0,
        "Grid_FL_MVA_sig": 855.0,
        "Grid_X2R_sig": 5.0,
        "Is_Infinite": False,
        "Inverters_In_Service": inverter_count,
        "Temperature_degC": temperature,
        "TAP_RATIO": tap_ratio,
        "Post_Init_Duration_s": 6.0,
    }
    scenario = Scenario("MFRT", 2, name, True, values)
    event = Event(event_time, 0, "fault_apply", {"type_code": 7})
    return StudyPlan(scenario, [event])


class _Backend:
    def __init__(self):
        self.initializations = []
        self.dispatch_calls = 0
        self.save_calls = 0
        self.save_paths = []

    def initialize(self, sav_path, log_stem, solve_load_flow=True):
        self.initializations.append((Path(sav_path).name, bool(solve_load_flow)))

    def configure_scenario_options(self, scenario):
        pass

    def configure_grid(self, scenario):
        return 0.01, 0.1

    def dispatch(self, scenario, r_pu, x_pu):
        self.dispatch_calls += 1

    def make_grid_infinite(self):
        pass

    def save_case(self, sav_path):
        self.save_calls += 1
        self.save_paths.append(Path(sav_path))
        Path(sav_path).write_bytes(b"solved dispatched sav")

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


class DispatchCacheTests(unittest.TestCase):
    def test_same_initial_state_is_grouped_despite_different_dynamic_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config(root, root / "cache")
            plans = [_plan("case_1", event_time=5.0), _plan("case_2", event_time=7.0)]
            plan = create_dispatch_plan(plans, config)
            self.assertEqual(len(plan.groups), 1)
            self.assertEqual(len(plan.groups[0].plans), 2)

    def test_profile_and_numeric_initial_power_share_dispatch_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config(root, root / "cache")
            numeric = _plan("numeric")
            profiled = _plan("profiled")
            profiled.scenario.values["Ppoc_MW_sig"] = (
                "285, AT 5s ↓ 142.5, at 15s ↓ 14.25, AT 25s ↑ 285"
            )
            plan = create_dispatch_plan([numeric, profiled], config)
            self.assertEqual(len(plan.groups), 1)
            self.assertEqual(plan.groups[0].signature["p_target_mw"], 285.0)

    def test_inverter_count_temperature_and_tap_prevent_unsafe_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config(root, root / "cache")
            plans = [
                _plan("base", inverter_count=100, temperature=25.0),
                _plan("fewer_inverters", inverter_count=80, temperature=25.0),
                _plan("hot", inverter_count=100, temperature=50.0),
                _plan("different_tap", inverter_count=100, temperature=25.0, tap_ratio=1.025),
            ]
            plan = create_dispatch_plan(plans, config)
            self.assertEqual(len(plan.groups), 4)
            self.assertIn("Inverters_In_Service", plan.extra_columns)
            self.assertIn("Temperature_degC", plan.extra_columns)
            self.assertIn("TAP_RATIO", plan.extra_columns)

    def test_model_change_uses_a_new_cache_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config(root, root / "cache")
            group = create_dispatch_plan([_plan("case")], config).groups[0]
            first = DispatchCache(config, root / "cache")
            target = first.target_path(group)
            target.write_bytes(b"solved")
            first.record_success(group, target)
            self.assertEqual(first.cached_path(group), target)

            (root / "model" / "base.sav").write_bytes(b"base sav v2")
            second = DispatchCache(config, root / "cache")
            self.assertNotEqual(first.directory, second.directory)
            self.assertIsNone(second.cached_path(group))

    def test_engine_dispatches_once_then_reuses_saved_case_across_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = _config(root, root / "cache")
            plans = [_plan("case_1"), _plan("case_2", event_time=5.5)]

            def fake_out_to_csv(out_path, csv_path, dyntools, nominal_frequency_hz):
                Path(csv_path).write_text("time,P\n0,0\n", encoding="utf-8")

            first = StudyEngine.__new__(StudyEngine)
            first.config = config
            first.psspy = object()
            first.dyntools = object()
            first.hooks = None
            first.backend = _Backend()
            first.reporter = ConsoleReporter(level="quiet", print_case_spec=False)
            with patch("psse_open.engine.out_to_csv", side_effect=fake_out_to_csv):
                first_results = first.run(plans)

            self.assertEqual(first.backend.dispatch_calls, 1)
            self.assertEqual(first.backend.save_calls, 1)
            staged = first.backend.save_paths[0]
            self.assertEqual(staged.parent.name.startswith("hbess_psse_"), True)
            self.assertFalse(staged.name.startswith("."))
            self.assertTrue(staged.name.endswith("_tmp.sav"))
            self.assertNotIn(".tmp.sav", staged.name)
            self.assertEqual(first.backend.initializations.count(("base.sav", True)), 1)
            self.assertEqual(sum(not solved for _name, solved in first.backend.initializations), 2)
            self.assertTrue(all(item["status"] == "completed" for item in first_results))
            self.assertEqual({item["dispatch_cache_status"] for item in first_results}, {"built"})

            second = StudyEngine.__new__(StudyEngine)
            second.config = config
            second.psspy = object()
            second.dyntools = object()
            second.hooks = None
            second.backend = _Backend()
            second.reporter = ConsoleReporter(level="quiet", print_case_spec=False)
            with patch("psse_open.engine.out_to_csv", side_effect=fake_out_to_csv):
                second_results = second.run(plans)

            self.assertEqual(second.backend.dispatch_calls, 0)
            self.assertEqual(second.backend.save_calls, 0)
            self.assertEqual(len(second.backend.initializations), 2)
            self.assertTrue(all(not solved for _name, solved in second.backend.initializations))
            self.assertEqual({item["dispatch_cache_status"] for item in second_results}, {"hit"})


if __name__ == "__main__":
    unittest.main()
