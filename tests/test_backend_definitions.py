import json
import math
import unittest
from pathlib import Path

from psse_open.backend import PsseBackend, PsseError
from psse_open.commands import parse_psse_commands
from psse_open.config import ProjectConfig
from psse_open.models import Scenario


class FakePsspy(object):
    def __init__(self):
        self.calls = []
        self.machine_values = {}

    def getdefaultint(self):
        return -999

    def getdefaultreal(self):
        return 0.0

    def getdefaultchar(self):
        return ""

    def _record(self, name, *args):
        self.calls.append((name, args))
        return 0

    def voltage_and_angle_channel(self, *args):
        return self._record("voltage", *args)

    def branch_p_and_q_channel(self, *args):
        return self._record("branch", *args)

    def var_channel(self, *args):
        return self._record("var", *args)

    def state_channel(self, *args):
        return self._record("state", *args)

    def machine_array_channel(self, *args):
        return self._record("machine", *args)

    def bus_frequency_channel(self, *args):
        return self._record("frequency", *args)

    def cctmind_buso(self, *args):
        self.calls.append(("cctmind_buso", args))
        return 0, 1000

    def mdlind(self, *args):
        self.calls.append(("mdlind", args))
        return 0, 2000

    def busdat(self, bus, item):
        return 0, 275.0

    def fixed_shunt_chng_3(self, *args):
        return self._record("fixed_shunt", *args)

    def fnsl(self, *args):
        return self._record("fnsl", *args)

    def plant_data(self, *args):
        return self._record("plant_data", *args)

    def brnmsc(self, _from_bus, _to_bus, _ckt, quantity):
        offset = 0 if str(quantity).upper() == "P" else 1
        return 0, sum(values[offset] for values in self.machine_values.values())

    def macdat(self, bus, machine_id, quantity):
        values = self.machine_values.setdefault((int(bus), str(machine_id)), [0.0, 0.0])
        return 0, values[0 if str(quantity).upper() == "P" else 1]

    def machine_data_2(self, bus, machine_id, _integers, reals):
        self.machine_values[(int(bus), str(machine_id))] = [float(reals[0]), float(reals[1])]
        return self._record("machine_data_2", bus, machine_id, _integers, reals)


class FixedShuntFakePsspy(FakePsspy):
    def __init__(self, fixed_shunts=None):
        super().__init__()
        self.fixed_shunts = dict(fixed_shunts or {})

    def fxsint(self, bus, shunt_id, field):
        self.calls.append(("fxsint", (bus, shunt_id, field)))
        key = (int(bus), str(shunt_id))
        if key not in self.fixed_shunts:
            return 2, None
        return 0, self.fixed_shunts[key]["status"]

    def fixed_shunt_data_3(self, bus, shunt_id, integers, reals, name):
        self.calls.append(
            ("fixed_shunt_data_3", (bus, shunt_id, integers, reals, name))
        )
        key = (int(bus), str(shunt_id))
        if key in self.fixed_shunts:
            return 4
        self.fixed_shunts[key] = {
            "status": int(integers[0]),
            "g": float(reals[0]),
            "b": float(reals[1]),
        }
        return 0

    def fixed_shunt_chng_3(self, bus, shunt_id, integers, reals, name):
        self.calls.append(
            ("fixed_shunt", (bus, shunt_id, integers, reals, name))
        )
        key = (int(bus), str(shunt_id))
        if key not in self.fixed_shunts:
            return 5
        shunt = self.fixed_shunts[key]
        shunt["status"] = int(integers[0])
        if reals != [self.getdefaultreal()] * 2:
            shunt["g"] = float(reals[0])
            shunt["b"] = float(reals[1])
        return 0


class LegacyFixedShuntFakePsspy(FixedShuntFakePsspy):
    fixed_shunt_data_3 = None

    def shunt_data(self, bus, shunt_id, status, reals):
        self.calls.append(("shunt_data", (bus, shunt_id, status, reals)))
        self.fixed_shunts[(int(bus), str(shunt_id))] = {
            "status": int(status),
            "g": float(reals[0]),
            "b": float(reals[1]),
        }
        return 0


class BackendDefinitionTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        definition = json.loads((root / "examples" / "definitions" / "HBESS.chandef").read_text(encoding="utf-8"))
        data = {
            "system": {
                "poc_bus": 100100,
                "infinite_bus": 100000,
                "fault_bus": 888888,
                "grid_branch": {"from_bus": 100000, "to_bus": 100100, "id": "1"},
                "infinite_machine": {"id": "1"},
                "fixed_shunts": {"tov": {"bus": 888888, "id": "1"}},
            },
            "dynamics": {"frequency_hz": 50.0},
            "channel_definition": definition,
        }
        self.fake = FakePsspy()
        self.backend = PsseBackend(self.fake, ProjectConfig(str(root / "test.json"), data))

    def test_exact_chandef_is_mapped_to_public_channel_calls(self):
        self.backend.add_channels()
        counts = {}
        for name, _args in self.fake.calls:
            counts[name] = counts.get(name, 0) + 1
        self.assertEqual(counts["voltage"], 4)
        self.assertEqual(counts["branch"], 28)
        self.assertEqual(counts["var"], 14)
        self.assertEqual(counts["machine"], 8)
        self.assertEqual(counts["frequency"], 1)
        labels = [args[1] for name, args in self.fake.calls if name == "var"]
        self.assertIn("PPOC_REF_MW", labels)
        self.assertIn("QINV_OUT_2", labels)

    def test_tov_capacitance_is_converted_to_fixed_shunt_mvar(self):
        self.backend.apply_tov_shunt({"capacitance_uf": 100.0}, True)
        call = [args for name, args in self.fake.calls if name == "fixed_shunt"][-1]
        expected = 2.0 * math.pi * 50.0 * 100.0e-6 * 275.0 * 275.0
        self.assertEqual(call[0:3], (888888, "1", [1]))
        self.assertAlmostEqual(call[3][1], expected)

    def test_fixed_shunt_command_events_use_named_project_configuration(self):
        events = parse_psse_commands(
            "CHANGE FIXED_SHUNT 'TOV' MVAR TO 1109.70957536556 AT 0.5s; "
            "TRIP FIXED_SHUNT 'TOV' AT 0.93s"
        )
        scenario = Scenario("5255_TOV", 2, "shunt_tov", True, {})
        for event in events:
            self.backend.apply_event(event, scenario)

        calls = [args for name, args in self.fake.calls if name == "fixed_shunt"]
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0:3], (888888, "1", [1]))
        self.assertAlmostEqual(calls[0][3][1], 1109.70957536556)
        self.assertEqual(calls[1][0:3], (888888, "1", [0]))
        self.assertEqual(calls[1][3], [self.fake.getdefaultreal()] * 2)

    def test_unknown_fixed_shunt_alias_is_rejected(self):
        with self.assertRaisesRegex(PsseError, "system.fixed_shunts"):
            self.backend.apply_fixed_shunt_change(
                {"shunt": "missing", "mvar": 100.0}
            )

    def _fixed_shunt_backend(self, physical_shunts=None, aliases=None):
        root = Path(__file__).resolve().parents[1]
        data = {
            "system": {
                "fixed_shunts": aliases
                if aliases is not None
                else {"tov": {"bus": 888888, "id": "1"}},
            },
            "dynamics": {"frequency_hz": 50.0},
        }
        fake = FixedShuntFakePsspy(physical_shunts)
        backend = PsseBackend(fake, ProjectConfig(str(root / "test.json"), data))
        return backend, fake

    def test_missing_tov_shunt_is_created_off_with_zero_admittance(self):
        backend, fake = self._fixed_shunt_backend()

        self.assertTrue(backend.ensure_tov_fixed_shunt())

        self.assertEqual(
            fake.fixed_shunts[(888888, "1")],
            {"status": 0, "g": 0.0, "b": 0.0},
        )
        create_calls = [
            args for name, args in fake.calls if name == "fixed_shunt_data_3"
        ]
        self.assertEqual(create_calls, [(888888, "1", [0], [0.0, 0.0], "")])

    def test_existing_tov_shunt_is_reused_without_overwrite(self):
        original = {"status": 1, "g": 2.0, "b": 3.0}
        backend, fake = self._fixed_shunt_backend(
            {(888888, "1"): dict(original)}
        )

        self.assertFalse(backend.ensure_tov_fixed_shunt())

        self.assertEqual(fake.fixed_shunts[(888888, "1")], original)
        self.assertFalse(
            any(name == "fixed_shunt_data_3" for name, _args in fake.calls)
        )

    def test_psse34_shunt_data_fallback_creates_zero_off_placeholder(self):
        root = Path(__file__).resolve().parents[1]
        fake = LegacyFixedShuntFakePsspy()
        config = ProjectConfig(str(root / "test.json"), {
            "system": {"fixed_shunts": {"tov": {"bus": 888888, "id": "1"}}},
            "dynamics": {},
        })
        backend = PsseBackend(fake, config)

        self.assertTrue(backend.ensure_tov_fixed_shunt())

        calls = [args for name, args in fake.calls if name == "shunt_data"]
        self.assertEqual(calls, [(888888, "1", 0, [0.0, 0.0])])

    def test_tov_creation_failure_identifies_alias_bus_id_and_error(self):
        backend, fake = self._fixed_shunt_backend()

        def fail_create(*args):
            return 7

        fake.fixed_shunt_data_3 = fail_create
        with self.assertRaisesRegex(
            PsseError,
            r"alias 'tov' at bus 888888 ID '1'; PSS/E error 7",
        ):
            backend.ensure_tov_fixed_shunt()

    def test_change_and_trip_use_the_ensured_tov_placeholder(self):
        backend, fake = self._fixed_shunt_backend()
        backend.ensure_tov_fixed_shunt()

        backend.apply_fixed_shunt_change({"shunt": "tov", "mvar": 1109.709})
        self.assertEqual(
            fake.fixed_shunts[(888888, "1")],
            {"status": 1, "g": 0.0, "b": 1109.709},
        )

        backend.apply_fixed_shunt_trip({"shunt": "tov"})
        self.assertEqual(fake.fixed_shunts[(888888, "1")]["status"], 0)
        self.assertEqual(fake.fixed_shunts[(888888, "1")]["b"], 1109.709)

    def test_missing_tov_alias_has_clear_error(self):
        backend, _fake = self._fixed_shunt_backend(aliases={})
        with self.assertRaisesRegex(
            PsseError,
            "Configured automation TOV shunt alias 'tov' is not defined",
        ):
            backend.ensure_tov_fixed_shunt()

    def test_existing_arbitrary_fixed_shunt_keeps_normal_change_behaviour(self):
        aliases = {"network_cap": {"bus": 777777, "id": "A"}}
        physical = {(777777, "A"): {"status": 0, "g": 0.0, "b": 25.0}}
        backend, fake = self._fixed_shunt_backend(physical, aliases)

        backend.apply_fixed_shunt_change(
            {"shunt": "network_cap", "mvar": 50.0}
        )

        self.assertEqual(
            fake.fixed_shunts[(777777, "A")],
            {"status": 1, "g": 0.0, "b": 50.0},
        )

    def test_missing_arbitrary_fixed_shunt_is_not_auto_created(self):
        aliases = {"network_cap": {"bus": 777777, "id": "A"}}
        backend, fake = self._fixed_shunt_backend({}, aliases)

        with self.assertRaisesRegex(PsseError, "PSS/E error 5"):
            backend.apply_fixed_shunt_change(
                {"shunt": "network_cap", "mvar": 50.0}
            )

        self.assertEqual(fake.fixed_shunts, {})
        self.assertFalse(
            any(name == "fixed_shunt_data_3" for name, _args in fake.calls)
        )

    def test_dispatch_uses_initdef_weights_and_pins_reactive_target(self):
        generators = [
            {
                "bus": 100111 + index * 100000,
                "id": "1",
                "p_weight": 0.25,
                "q_weight": 0.25,
                "pmin_mw": -105.8,
                "pmax_mw": 105.8,
                "qmin_mvar": -105.8,
                "qmax_mvar": 105.8,
            }
            for index in range(4)
        ]
        data = {
            "bases": {"p_mw": 285.0, "q_mvar": 112.575, "normal_v_pu": 1.06},
            "system": {
                "poc_bus": 100100,
                "infinite_bus": 100000,
                "grid_branch": {"from_bus": 100000, "to_bus": 100100, "id": "1"},
                "measurement_branch": {"from_bus": 100100, "to_bus": 100000, "id": "1"},
                "infinite_machine": {"id": "1"},
                "generators": generators,
            },
            "load_flow": {
                "solve_repetitions": 1,
                "max_iterations": 5,
                "p_tolerance_mw": 0.1,
                "q_tolerance_mvar": 0.1,
                "correction_gain": 1.0,
            },
            "dynamics": {},
        }
        fake = FakePsspy()
        backend = PsseBackend(fake, ProjectConfig("test.json", data))
        scenario = Scenario("sheet", 2, "case", True, {
            "Ppoc_MW_sig": "100, AT 5s ↓ 50",
            "Qpoc_MVAr_init": "40, AT 5s ↓ 20",
            "Vpoc_pu_sig": "1.06, AT 5s ↓ 1.01",
        })
        backend.dispatch(scenario, 0.01, 0.1)
        self.assertEqual([value for value in fake.machine_values.values()], [[25.0, 10.0]] * 4)
        machine_calls = [args for name, args in fake.calls if name == "machine_data_2"]
        self.assertTrue(all(args[3][1:4] == [10.0, 10.0, 10.0] for args in machine_calls[-4:]))


if __name__ == "__main__":
    unittest.main()
