import unittest

import pandas as pd

from hbess_open.plotting.process_and_calc_psse import pre_process_dataframe


class PreprocessingTests(unittest.TestCase):
    def test_frt_hysteresis_and_transformer_voltage_ratio(self):
        frame = pd.DataFrame({
            "V_HYBESS_PU": [1.0, 0.84, 0.8505, 0.86, 1.19, 1.17],
            "POC_F_PU": [0.0] * 6,
            "V_POC_PU": [1.0] * 6,
            "V_MV_PU": [0.5] * 6,
            "PPOC_MW": [10.0] * 6,
            "QPOC_MVAR": [2.0] * 6,
            "PMEAS_INV_PU": [0.1] * 6,
            "QMEAS_INV_PU": [0.02] * 6,
        })
        result = pre_process_dataframe(frame)
        self.assertEqual(result["INV_FRT"].tolist(), [0.0, 1.0, 1.0, 0.0, 1.0, 0.0])
        self.assertTrue((result["Main_Tx_HVMV_Ratio"] == 2.0).all())


if __name__ == "__main__":
    unittest.main()
