import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from hbess_open.analysis.gridlink.settling_analysis import analyse_step
from hbess_open.io.psse_out import out_to_df
from hbess_open.io.signal_dsl import ParsedSignal
from hbess_open.open_psse.plot_adapter import invoke_project_plotter
from hbess_open.plotting.replotters import replot_psse


class _RecordingPlotter:
    def __init__(self):
        self.calls = []

    def plot_from_df_and_dict(self, df, scenario_dict, png_path, pdf_path):
        self.calls.append((df, scenario_dict, png_path, pdf_path))
        Path(png_path).write_bytes(b"png")
        Path(pdf_path).write_bytes(b"pdf")


class _MissingChannelPlotter:
    def plot_from_df_and_dict(self, df, scenario_dict, png_path, pdf_path):
        raise KeyError("PPOC_MW")


class PostProcessingTests(unittest.TestCase):
    def test_native_dsl_parser_exposes_pallet_compatible_pieces(self):
        signal = ParsedSignal.parse("0, AT 0.5s, ↑ 1, AT 0.93s ↓ 0").signal
        self.assertEqual(signal.initial_value, 0.0)
        self.assertEqual([(item.time_start, item.target) for item in signal.pieces], [(0.5, 1.0), (0.93, 0.0)])

    def test_out_reader_prefers_adjacent_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            out_path = Path(directory) / "case.out"
            out_path.write_bytes(b"not a real out")
            pd.DataFrame({"time": [0.0, 1.0], "P": [1.0, 2.0]}).to_csv(out_path.with_suffix(".csv"), index=False)
            frame = out_to_df(out_path)
            self.assertEqual(frame.index.tolist(), [0.0, 1.0])
            self.assertEqual(frame["P"].tolist(), [1.0, 2.0])

    def test_step_metrics_handle_monotonic_response(self):
        series = pd.Series([0.0, 0.2, 0.7, 0.95, 1.0, 1.0], index=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5])
        result = analyse_step(series)
        self.assertLess(result.rise_time_results.rise_time_sec, 1.0)
        self.assertLess(result.settling_time_results.settling_time_sec, 1.0)

    def test_replot_pairs_out_csv_and_json_by_stem(self):
        with tempfile.TemporaryDirectory() as input_directory, tempfile.TemporaryDirectory() as output_directory:
            category = Path(input_directory) / "CSR Test"
            category.mkdir()
            (category / "case_001.out").write_bytes(b"out")
            pd.DataFrame({"time": [0.0, 1.0], "P": [1.0, 2.0]}).to_csv(category / "case_001.csv", index=False)
            (category / "case_001.json").write_text(json.dumps({"File_Name": "case_001"}), encoding="utf-8")
            plotter = _RecordingPlotter()
            results = replot_psse(".out", plotter, input_directory, output_directory, True)
            self.assertEqual(len(results), 1)
            self.assertEqual(plotter.calls[0][1]["File_Name"], "case_001")
            self.assertTrue((Path(output_directory) / "CSR Test" / "case_001.png").exists())

    def test_plot_adapter_reports_missing_chandef_channel(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "case.csv"
            pd.DataFrame({"time": [0.0], "V": [1.0]}).to_csv(csv_path, index=False)
            with self.assertRaisesRegex(RuntimeError, "needs channel 'PPOC_MW'"):
                invoke_project_plotter(
                    _MissingChannelPlotter(),
                    str(csv_path),
                    {"File_Name": "case"},
                    directory,
                )


if __name__ == "__main__":
    unittest.main()
