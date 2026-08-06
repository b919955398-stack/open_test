from psse_open.profiles import combine_playback, initial_signal_value, parse_signal_profile
import unittest


class ProfileTests(unittest.TestCase):
    def test_ramp_profile(self):
        points = parse_signal_profile("50, FROM 5s TO 8s ↗ 52, FROM 15s TO 18s ↘ 50")
        self.assertEqual(points, [(0.0, 50.0), (5.0, 50.0), (8.0, 52.0), (15.0, 52.0), (18.0, 50.0)])

    def test_step_profile(self):
        self.assertEqual(parse_signal_profile("1.06, AT 5s ↓ 1.01")[-1], (5.0, 1.01))

    def test_combined_profile_interpolates_other_signal(self):
        points = combine_playback([(0.0, 1.0), (10.0, 1.1)], [(0.0, 50.0), (5.0, 51.0)])
        self.assertAlmostEqual(points[1].voltage_pu, 1.05)

    def test_profile_scaling_is_applied(self):
        points = parse_signal_profile("1, AT 2s ↑ 1.1, WITH SCALING=1.05")
        self.assertEqual(points[0], (0.0, 1.05))
        self.assertAlmostEqual(points[-1][1], 1.155)

    def test_step_profile_accepts_comma_before_arrow(self):
        points = parse_signal_profile("0, AT 0.5s, ↑ 1, AT 0.93s ↓ 0")
        self.assertEqual(points[-3:], [(0.5, 1.0), (0.929, 1.0), (0.93, 0.0)])

    def test_initial_signal_value_uses_profile_time_zero_value(self):
        value = initial_signal_value(
            "285, AT 5s ↓ 142.5, at 15s ↓ 14.25, AT 25s ↑ 285"
        )
        self.assertEqual(value, 285.0)
