import os
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

    def _record(self, name, *args):
        self.calls.append((name, args))
        return 0

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

    def psseinit(self, buses):
        return self._record("psseinit", buses)

    def case(self, path):
        return self._record("case", path)

    def fnsl(self, options):
        return self._record("fnsl", options)

    def pssehalt_2(self):
        return self._record("halt")

    def save(self, path):
        return self._record("save", path)


class _DynamicFakePsspy(_FakePsspy):
    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return 0

        return method


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

    def test_halt_is_only_sent_after_successful_psse_initialization(self):
        fake = _FakePsspy()
        config = ProjectConfig("test.json", {
            "system": {},
            "dynamics": {},
            "psse": {"max_buses": 1000},
            "load_flow": {"solve_repetitions": 1},
            "psse_output_mode": "quiet",
        })
        backend = PsseBackend(fake, config)

        backend.halt()
        self.assertEqual([call[0] for call in fake.calls].count("halt"), 0)

        backend.initialize(Path("base.sav"), Path("case"))
        backend.halt()
        backend.halt()
        self.assertEqual([call[0] for call in fake.calls].count("halt"), 1)

    def test_save_uses_plain_relative_name_when_target_is_in_current_directory(self):
        fake = _FakePsspy()
        config = ProjectConfig("test.json", {"system": {}, "dynamics": {}})
        backend = PsseBackend(fake, config)
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory).resolve()
            try:
                os.chdir(str(runtime))
                backend.save_case(runtime / "dispatch_abc_123_tmp.sav")
            finally:
                os.chdir(str(previous))
        save_calls = [args for name, args in fake.calls if name == "save"]
        self.assertEqual(save_calls, [("dispatch_abc_123_tmp.sav",)])

    def test_initialised_sav_is_saved_with_short_name_before_strt(self):
        fake = _DynamicFakePsspy()
        config = ProjectConfig("test.json", {
            "system": {},
            "dynamics": {},
            "channel_definition": {"bus_voltage_channels": []},
        })
        backend = PsseBackend(fake, config)
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory).resolve()
            dyr_path = runtime / "base.dyr"
            dyr_path.write_text("/\n", encoding="ascii")
            try:
                os.chdir(str(runtime))
                backend.initialize_dynamics(
                    runtime,
                    dyr_path,
                    runtime / "case.out",
                    [],
                    initialised_sav_path=runtime / "initialised_123_0001.sav",
                )
            finally:
                os.chdir(str(previous))

        call_names = [call[0] for call in fake.calls]
        self.assertLess(call_names.index("save"), call_names.index("strt"))
        save_calls = [call[1] for call in fake.calls if call[0] == "save"]
        self.assertEqual(save_calls, [("initialised_123_0001.sav",)])


if __name__ == "__main__":
    unittest.main()
