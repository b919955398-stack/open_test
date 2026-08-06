import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from hbess_open.initialisation import (
    calculate_tov_shunt_mvar,
    calculate_vslack_pu,
    prepare_pscad_spec,
    shunt_mvar_to_capacitance_uf,
)


class PscadInitialisationTests(unittest.TestCase):
    @staticmethod
    def _spec():
        return pd.DataFrame(
            {
                "File_Name": ["tov_case", "zero_impedance"],
                "Grid_FL_MVA_sig": [5591.0, -1.0],
                "Grid_X2R_sig": [12.04, -1.0],
                "Vpoc_pu_sig": [1.06, 1.0],
                "Ppoc_MW_sig": [285.0, 285.0],
                "Qpoc_MVAr_init": [0.0, 0.0],
                "Ppoc_pu": [1.0, 1.0],
                "Qpoc_pu": [0.0, 0.0],
                "Vslack_pu_sig": [
                    "1, AT 0.5s UP 1.1, WITH SCALING=$VSLACK",
                    None,
                ],
                # This mirrors the supplied workbook: global True must still
                # calculate valid U_Ov rows when every row flag is False.
                "Calc_TOV": [False, False],
                "U_Ov": [1.2, None],
                "TOV_MVAr": [None, None],
                "TOV_Shunt_C_uF_sig": [None, None],
            }
        )

    def test_vslack_matches_the_legacy_two_bus_convention(self):
        calculated = calculate_vslack_pu(5591.0, 10.0, 1.06, -285.0, 0.0)
        # Value captured from the supplied legacy skip_spec.csv.  The small
        # tolerance covers Pallet/pandapower's iterative load-flow tolerance.
        self.assertTrue(math.isclose(calculated, 1.065891, abs_tol=1e-4))

    def test_tov_is_zero_at_initial_voltage_and_positive_for_overvoltage(self):
        unchanged = calculate_tov_shunt_mvar(
            5591.0,
            12.04,
            1.06,
            285.0,
            0.0,
            1.06,
        )
        raised = calculate_tov_shunt_mvar(
            5591.0,
            12.04,
            1.06,
            285.0,
            0.0,
            1.2,
        )
        self.assertAlmostEqual(unchanged, 0.0, places=9)
        self.assertTrue(math.isclose(raised, 653.706239, rel_tol=1e-8))
        self.assertGreater(shunt_mvar_to_capacitance_uf(raised, 275.0, 50.0), 0.0)

    def test_preparation_expands_placeholder_calculates_tov_and_writes_compact_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache_path = Path(temporary) / "vslack_cache.csv"
            result = prepare_pscad_spec(
                self._spec(),
                use_vslack_cache=False,
                calc_tov_shunt_var=True,
                cache_path=str(cache_path),
                pbase_mw=285.0,
                qbase_mvar=112.575,
                verbose=False,
            )
            self.assertNotIn("$VSLACK", result.loc[0, "Vslack_pu_sig"])
            self.assertAlmostEqual(result.loc[1, "constant_vslack_pu_sig"], 1.0)
            self.assertGreater(result.loc[0, "TOV_MVAr"], 0.0)
            self.assertTrue(cache_path.is_file())
            self.assertFalse(any(name.endswith("_from_cache") for name in result.columns))

            cache = pd.read_csv(cache_path)
            self.assertEqual(len(cache), 2)
            self.assertIn("Ppoc_MW", cache.columns)
            self.assertIn("Qpoc_MVAr", cache.columns)

    def test_cache_is_used_and_tov_false_preserves_cached_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache_path = Path(temporary) / "vslack_cache.csv"
            prepared = prepare_pscad_spec(
                self._spec(),
                cache_path=str(cache_path),
                calc_tov_shunt_var=True,
                pbase_mw=285.0,
                qbase_mvar=112.575,
                verbose=False,
            )
            source = self._spec()
            reused = prepare_pscad_spec(
                source,
                use_vslack_cache=True,
                calc_tov_shunt_var=False,
                cache_path=str(cache_path),
                pbase_mw=285.0,
                qbase_mvar=112.575,
                verbose=False,
            )
            self.assertAlmostEqual(
                reused.loc[0, "constant_vslack_pu_sig"],
                prepared.loc[0, "constant_vslack_pu_sig"],
            )
            self.assertAlmostEqual(
                reused.loc[0, "TOV_MVAr"],
                prepared.loc[0, "TOV_MVAr"],
            )
            self.assertEqual(
                reused.attrs["pscad_initialisation"]["vslack_cache_hits"],
                2,
            )

    def test_legacy_per_unit_cache_columns_are_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache_path = Path(temporary) / "vslack_cache.csv"
            pd.DataFrame(
                {
                    "Grid_FL_MVA_sig": [5591.0],
                    "Grid_X2R_sig": [12.04],
                    "Vpoc_pu_sig": [1.06],
                    "Ppoc_pu": [1.0],
                    "Qpoc_pu": [0.0],
                    "U_Ov": [1.2],
                    "Vslack_pu_sig": [1.2345],
                    "TOV_MVAr": [900.0],
                    "TOV_Shunt_C_uF_sig": [37.0],
                }
            ).to_csv(cache_path, index=False)
            result = prepare_pscad_spec(
                self._spec().iloc[[0]],
                use_vslack_cache=True,
                calc_tov_shunt_var=False,
                cache_path=str(cache_path),
                pbase_mw=285.0,
                qbase_mvar=112.575,
                update_cache=False,
                verbose=False,
            )
            self.assertAlmostEqual(result.iloc[0]["constant_vslack_pu_sig"], 1.2345)
            self.assertAlmostEqual(result.iloc[0]["TOV_MVAr"], 900.0)


if __name__ == "__main__":
    unittest.main()
