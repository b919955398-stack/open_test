import shutil
import tempfile
import unittest
from pathlib import Path

from psse_open.definitions import load_or_build_project_config


class DefinitionTests(unittest.TestCase):
    def test_hbess_definitions_build_runnable_mapping(self):
        fixture_dir = Path(__file__).resolve().parents[1] / "examples" / "definitions"
        with tempfile.TemporaryDirectory() as temporary:
            model_dir = Path(temporary)
            for name in ("HBESS.savdef", "HBESS.initdef", "HBESS.chandef"):
                shutil.copy2(str(fixture_dir / name), str(model_dir / name))
            (model_dir / "model.sav").write_bytes(b"fixture")
            (model_dir / "model.dyr").write_text("/", encoding="ascii")
            config = load_or_build_project_config(str(model_dir))

        system = config.section("system")
        self.assertEqual(system["infinite_bus"], 100000)
        self.assertEqual(system["poc_bus"], 100100)
        self.assertEqual(system["fault_bus"], 888888)
        self.assertEqual(system["bus_aliases"]["3HYWDBS_275E"], 888888)
        self.assertEqual(system["measurement_branch"]["from_bus"], 100100)
        self.assertEqual(len(system["generators"]), 4)
        self.assertEqual(sum(item["p_weight"] for item in system["generators"]), 1.0)
        self.assertEqual(config.section("models")["flncppc"]["method"], "cctmind_buso")
        self.assertEqual(config.section("transformers")["phase_shift_tx"]["id"], "2")
        channels = config.section("channel_definition")
        self.assertEqual(len(channels["branch_pq_channels"]), 28)
        self.assertEqual(len(channels["var_channels"]), 14)


if __name__ == "__main__":
    unittest.main()
