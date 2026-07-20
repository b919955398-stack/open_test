import json
import math
import unittest
from pathlib import Path

from psse_open.backend import PsseBackend
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
            "Ppoc_MW_sig": 100.0, "Qpoc_MVAr_init": 40.0, "Vpoc_pu_sig": 1.06
        })
        backend.dispatch(scenario, 0.01, 0.1)
        self.assertEqual([value for value in fake.machine_values.values()], [[25.0, 10.0]] * 4)
        machine_calls = [args for name, args in fake.calls if name == "machine_data_2"]
        self.assertTrue(all(args[3][1:4] == [10.0, 10.0, 10.0] for args in machine_calls[-4:]))


if __name__ == "__main__":
    unittest.main()
