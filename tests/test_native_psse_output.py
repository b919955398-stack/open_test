import os
import tempfile
import unittest
from pathlib import Path

from psse_open.backend import PsseBackend
from psse_open.config import ProjectConfig
from psse_open.models import PlaybackPoint


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

    def test_each_case_gets_a_distinct_short_playback_file_stem(self):
        fake = _DynamicFakePsspy()
        config = ProjectConfig("test.json", {
            "system": {"infinite_bus": 99, "infinite_machine": {"id": "1"}},
            "dynamics": {"frequency_hz": 50.0},
            "channel_definition": {"bus_voltage_channels": []},
        })
        backend = PsseBackend(fake, config)
        playback = [
            PlaybackPoint(0.0, voltage_pu=1.0, frequency_hz=50.0),
            PlaybackPoint(0.5, voltage_pu=1.2, frequency_hz=50.0),
            PlaybackPoint(0.93, voltage_pu=1.0, frequency_hz=50.0),
        ]
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory).resolve()
            dyr_path = runtime / "base.dyr"
            dyr_path.write_text("/\n", encoding="ascii")
            try:
                os.chdir(str(runtime))
                first = backend.initialize_dynamics(
                    runtime, dyr_path, runtime / "CSR" / "case.out", playback
                )
                second = backend.initialize_dynamics(
                    runtime, dyr_path, runtime / "DMAT" / "case.out", playback
                )
            finally:
                os.chdir(str(previous))

            self.assertNotEqual(first["stem"], second["stem"])
            self.assertEqual(len(first["stem"]), 8)
            self.assertEqual(len(second["stem"]), 8)
            self.assertIn("'{}'".format(first["stem"]), Path(first["dyr_path"]).read_text())
            self.assertIn("'{}'".format(second["stem"]), Path(second["dyr_path"]).read_text())
            self.assertGreater(first["voltage_span_pu"], 0.1)

    def test_write_playback_serializes_each_profile_into_its_own_plb(self):
        fake = _DynamicFakePsspy()
        config = ProjectConfig("test.json", {
            "system": {"infinite_bus": 99, "infinite_machine": {"id": "1"}},
            "dynamics": {"frequency_hz": 50.0},
        })
        backend = PsseBackend(fake, config)
        first_profile = [
            PlaybackPoint(0.0, voltage_pu=1.0, frequency_hz=50.0),
            PlaybackPoint(1.0, voltage_pu=1.1, frequency_hz=50.5),
        ]
        second_profile = [
            PlaybackPoint(0.0, voltage_pu=1.0, frequency_hz=50.0),
            PlaybackPoint(1.0, voltage_pu=0.9, frequency_hz=49.5),
        ]

        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            first_path, _, _ = backend._write_playback(
                runtime, first_profile, file_stem="first"
            )
            second_path, _, _ = backend._write_playback(
                runtime, second_profile, file_stem="second"
            )

            self.assertEqual(
                first_path.read_text(encoding="ascii"),
                "0 1 50\n1 1.1 50.5\n99999 1.1 50.5\n",
            )
            self.assertEqual(
                second_path.read_text(encoding="ascii"),
                "0 1 50\n1 0.9 49.5\n99999 0.9 49.5\n",
            )
            self.assertNotEqual(first_path.read_bytes(), second_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
