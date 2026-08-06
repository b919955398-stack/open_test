import io
import unittest

from psse_open.progress import ConsoleReporter


class ProgressReporterTests(unittest.TestCase):
    def test_command_output_is_plain_text_with_stable_prefixes(self):
        stream = io.StringIO()
        reporter = ConsoleReporter(
            level="commands",
            print_case_spec=True,
            spec_fields=["File_Name", "Grid_SCR"],
            stream=stream,
        )
        reporter.case_spec({"File_Name": "case_1", "Grid_SCR": 1.2})
        reporter.command("[1/2] case_1", "FAULT APPLY", {"time": 5.0})
        value = stream.getvalue()
        self.assertIn("[SPEC] SPEC | File_Name=case_1 | Grid_SCR=1.2", value)
        self.assertIn("[COMMAND] [1/2] case_1 FAULT APPLY", value)
        self.assertNotIn("\x1b", value)

    def test_cases_level_suppresses_spec_and_command_detail(self):
        stream = io.StringIO()
        reporter = ConsoleReporter(level="cases", stream=stream)
        reporter.case_spec({"File_Name": "case_1"})
        reporter.command("case_1", "FAULT APPLY")
        reporter.emit("case_1 START", "heading", "cases")
        self.assertEqual(stream.getvalue(), "[BATCH] case_1 START\n")


if __name__ == "__main__":
    unittest.main()
