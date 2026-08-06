import tempfile
import unittest
from pathlib import Path

from psse_open.backend import PsseBackend
from psse_open.config import ProjectConfig


class _FakePsspy(object):
    def __init__(self):
        self.calls = []

    def getdefaultint(self):
        return -999

    def getdefaultreal(self):
        return 0.0

    def getdefaultchar(self):
        return ""

    def _output(self, name, selector, target, options):
        self.calls.append((name, selector, target, options))
        return 0

    def report_output(self, selector, target, options):
        return self._output("report", selector, target, options)

    def progress_output(self, selector, target, options):
        return self._output("progress", selector, target, options)

    def alert_output(self, selector, target, options):
        return self._output("alert", selector, target, options)

    def prompt_output(self, selector, target, options):
        return self._output("prompt", selector, target, options)


class NativePsseOutputTests(unittest.TestCase):
    def test_console_files_and_quiet_modes_use_expected_psse_selectors(self):
        expected = {"console": 1, "files": 2, "quiet": 6}
        with tempfile.TemporaryDirectory() as directory:
            stem = Path(directory) / "case"
            for mode, selector in expected.items():
                with self.subTest(mode=mode):
                    fake = _FakePsspy()
                    config = ProjectConfig("test.json", {
                        "system": {},
                        "dynamics": {},
                        "psse_output_mode": mode,
                    })
                    backend = PsseBackend(fake, config)
                    self.assertEqual(backend._configure_native_output(stem), mode)
                    self.assertEqual(len(fake.calls), 4)
                    self.assertTrue(all(call[1] == selector for call in fake.calls))
                    if mode == "files":
                        self.assertTrue(all(call[2].startswith(str(stem)) for call in fake.calls))
                    else:
                        self.assertTrue(all(call[2] == "" for call in fake.calls))

    def test_legacy_keep_logs_maps_to_files_when_mode_is_unspecified(self):
        fake = _FakePsspy()
        config = ProjectConfig("test.json", {
            "system": {},
            "dynamics": {},
            "keep_psse_logs": True,
        })
        backend = PsseBackend(fake, config)
        self.assertEqual(backend._configure_native_output(Path("case")), "files")
        self.assertTrue(all(call[1] == 2 for call in fake.calls))


if __name__ == "__main__":
    unittest.main()
