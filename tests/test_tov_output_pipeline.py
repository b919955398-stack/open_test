import unittest

import pandas as pd

from hbess_open.open_psse.plot_adapter import downsample_dataframe_for_plot
from psse_open.output import out_to_dataframe


class _ChannelFile:
    def get_data(self):
        return (
            "title",
            {1: "POC_FREQUENCY", 2: "INV_PELEC", 3: "V_POC_PU"},
            {
                "time": [0.0, 0.5],
                1: [0.0, 0.01],
                2: [0.25, 0.5],
                3: [1.0, 1.2],
            },
        )


class _DynTools:
    @staticmethod
    def CHNF(path, outvrsn=0):
        return _ChannelFile()


class TovOutputPipelineTests(unittest.TestCase):
    def test_out_is_decoded_directly_to_memory_with_unit_conversions(self):
        frame = out_to_dataframe("case.out", _DynTools(), nominal_frequency_hz=50.0)
        self.assertEqual(list(frame.columns), ["time", "POC_FREQUENCY", "INV_PELEC", "V_POC_PU"])
        self.assertEqual(frame["POC_FREQUENCY"].tolist(), [50.0, 50.5])
        self.assertEqual(frame["INV_PELEC"].tolist(), [25.0, 50.0])
        self.assertEqual(frame["V_POC_PU"].tolist(), [1.0, 1.2])

    def test_plot_downsampling_keeps_samples_around_tov_transitions(self):
        frame = pd.DataFrame({
            "time": [index / 1000.0 for index in range(10001)],
            "V_POC_PU": [1.0] * 10001,
        })
        reduced = downsample_dataframe_for_plot(
            frame, max_points=100, event_times=[0.5, 0.93]
        )
        kept_times = set(round(value, 3) for value in reduced["time"])
        for expected in (0.498, 0.499, 0.5, 0.501, 0.502, 0.928, 0.929, 0.93, 0.931, 0.932):
            self.assertIn(expected, kept_times)
        self.assertLessEqual(len(reduced), 110)


if __name__ == "__main__":
    unittest.main()
