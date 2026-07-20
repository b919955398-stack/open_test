from psse_open.commands import build_plan, parse_psse_commands
from psse_open.models import Scenario
import unittest


class CommandTests(unittest.TestCase):
    def test_parse_fault_and_grid_change(self):
        text = (
            "CHANGE BRANCH 'grid' FAULT_LEVEL AND X2R TO 342 AND 10 AT 0.5s; "
            "APPLY FAULT TO BUS '888888' AT 0.5s WITH TYPE=7, X2R=10, ZF2ZS=0.11, "
            "RF_OFFSET=0, XF_OFFSET=0, DURATION=0.43s, GRID_FL_MVA=342, GRID_X2R=10"
        )
        events = parse_psse_commands(text)
        self.assertEqual([event.kind for event in events], ["grid_strength", "fault_apply", "fault_clear"])
        self.assertAlmostEqual(events[-1].time, 0.93)

    def test_parse_model_drive_and_set(self):
        text = (
            "SET MODEL 'flncppc' ICON 6 TO 2 AT 0s; "
            "DRIVE MODEL 'flncppc' VAR 7 = AT 0s ↑ 0.95, AT 2s ↑ 1.0, WITH SCALING=0.98"
        )
        events = parse_psse_commands(text)
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].parameters["item"], "ICON")
        self.assertEqual(events[2].parameters["value"], 1.0)

    def test_parse_residual_voltage_fault_and_load_change(self):
        text = (
            "APPLY FAULT TO BUS '3HYWDBS_275E' AT 0.5s WITH TYPE=7, X2R=12.04, "
            "ZF2ZS=0, URES_PU=0.75, RF_OFFSET=0, XF_OFFSET=0, DURATION=0.22s; "
            "CHANGE LOAD 'PLR' MW TO -85.5 AT 5s"
        )
        events = parse_psse_commands(text)
        self.assertEqual([event.kind for event in events], ["fault_apply", "fault_clear", "load_change"])
        self.assertEqual(events[0].parameters["residual_voltage_pu"], 0.75)
        self.assertEqual(events[-1].parameters["value"], -85.5)

    def test_build_plan_resolves_vslack_placeholder(self):
        scenario = Scenario("sheet", 2, "case", True, {
            "Vslack_pu_psse": "1, AT 1s ↑ 1.05, WITH SCALING=$VSLACK",
            "Grid_FL_MVA_sig": 3185.0,
            "Grid_X2R_sig": 11.24,
            "Vpoc_pu_sig": 1.06,
            "Ppoc_MW_sig": 285.0,
            "Qpoc_MVAr_init": 0.0,
        })
        playback = build_plan(scenario).playback
        self.assertTrue(playback)
        self.assertGreater(playback[0].voltage_pu, 0.9)
        self.assertNotEqual(playback[0].voltage_pu, 1.0)
