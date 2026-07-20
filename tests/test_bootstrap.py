import unittest
from pathlib import Path
from unittest.mock import patch

from psse_open.bootstrap import psse_search_paths


class BootstrapTests(unittest.TestCase):
    def test_standard_psse34_python39_paths_are_derived(self):
        root = Path("/opt/PTI/PSSE34")
        existing = {
            str(root / "PSSPY39"),
            str(root / "PSSBIN"),
        }

        def is_dir(path):
            return str(path) in existing

        with patch("psse_open.bootstrap.sys.version_info", (3, 9, 0)), \
                patch("psse_open.bootstrap.Path.is_dir", is_dir):
            python_paths, bin_paths, attempted = psse_search_paths({"version": 34, "install_root": str(root)})

        self.assertEqual([path.name for path in python_paths], ["PSSPY39"])
        self.assertEqual([path.name for path in bin_paths], ["PSSBIN"])
        self.assertTrue(any("PSSE34" in str(path) for path in attempted))


if __name__ == "__main__":
    unittest.main()
