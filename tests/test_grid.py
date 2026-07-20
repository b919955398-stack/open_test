import math
import unittest

from psse_open.grid import fault_impedance_ohm, impedance_from_fault_level, infinite_bus_voltage


class GridTests(unittest.TestCase):
    def test_fault_level_impedance_magnitude_and_xr(self):
        r, x = impedance_from_fault_level(1000.0, 10.0)
        self.assertTrue(math.isclose(abs(complex(r, x)), 0.1, rel_tol=1e-12))
        self.assertTrue(math.isclose(x / r, 10.0, rel_tol=1e-12))

    def test_fault_impedance_from_zf_over_zs(self):
        r, x = fault_impedance_ohm(1.0, 10.0, zf_over_zs=0.25, fault_x_over_r=5.0)
        self.assertTrue(math.isclose(abs(complex(r, x)), abs(complex(1.0, 10.0)) * 0.25, rel_tol=1e-12))
        self.assertTrue(math.isclose(x / r, 5.0, rel_tol=1e-12))

    def test_infinite_bus_voltage_is_positive(self):
        self.assertGreater(infinite_bus_voltage(1.0, 100.0, 0.0, 0.01, 0.1), 0.0)
