import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from hbess_open.analysis.clause_analysis.s52511_dpdf_analysis import produce_s52511_dpdf_outputs
from hbess_open.analysis.clause_analysis.s5255_mfrt_analysis import produce_s5255_mfrt_outputs
from hbess_open.analysis.run_analysis_pscad import run_analysis_pscad
from hbess_open.io.pscad_out import PscadOut, psout_to_df
from hbess_open.io.result_data import result_to_df
from hbess_open.plotting.replotters import replot_pscad


class _Domain:
    data = [8.0, 9.0, 10.0]


class _Call:
    def __init__(self, name, parent=None):
        self.parent = parent
        self._name = name

    def variables(self):
        return {"Name": self._name}


class _Trace:
    def __init__(self, trace_id, name, data):
        self.id = trace_id
        self.data = data
        self.domain = _Domain()
        self.call = _Call("PGB:Data", _Call("Record", _Call(name)))

    def variables(self):
        return {}


class _Run:
    def traces(self):
        return iter([
            _Trace(1, "PLANT_P_HV", [0.0, 1.0, 2.0]),
            _Trace(2, "PLANT_Q_HV", [3.0, 4.0, 5.0]),
        ])


class _File:
    num_runs = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def run(self, index):
        if index != 0:
            raise IndexError(index)
        return _Run()


class _RecordingPlotter:
    def __init__(self):
        self.frames = []

    def plot_from_df_and_dict(self, df, scenario_dict, png_path, pdf_path):
        self.frames.append((df.copy(), dict(scenario_dict)))
        Path(png_path).write_bytes(b"png")
        Path(pdf_path).write_bytes(b"pdf")


class PscadPostProcessingTests(unittest.TestCase):
    def test_official_psout_shape_is_converted_without_pallet(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.psout"
            path.write_bytes(b"fixture")
            frame = PscadOut(
                path,
                prefer_cache=False,
                file_factory=lambda _path: _File(),
            ).to_df(secs_to_remove=9.0)
            self.assertEqual(frame.columns.tolist(), ["PLANT_P_HV", "PLANT_Q_HV"])
            self.assertEqual(frame.index.tolist(), [0.0, 1.0])
            self.assertEqual(frame["PLANT_P_HV"].tolist(), [1.0, 2.0])

    def test_psout_reader_prefers_adjacent_pickle_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.psout"
            path.write_bytes(b"not opened")
            pd.DataFrame({"P": [1.0, 2.0]}, index=[0.0, 1.0]).to_pickle(path.with_suffix(".pkl"))
            frame = psout_to_df(path)
            self.assertEqual(frame["P"].tolist(), [1.0, 2.0])

    def test_result_reader_trims_pscad_initialisation_time(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.psout"
            path.write_bytes(b"cache marker")
            pd.DataFrame({"time": [8.0, 9.0, 10.0], "P": [0.0, 1.0, 2.0]}).to_csv(
                path.with_suffix(".csv"), index=False
            )
            frame = result_to_df(path, platform="pscad", remove_first_seconds=9.0)
            self.assertEqual(frame.index.tolist(), [0.0, 1.0])
            self.assertEqual(frame["P"].tolist(), [1.0, 2.0])

    def test_existing_dpdf_clause_runs_on_pscad_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "case.psout"
            path.write_bytes(b"cache marker")
            pd.DataFrame({
                "time": [8.0, 8.5, 9.0, 9.5, 10.0],
                "Pref": [0.0, 0.0, 0.0, 0.0, 0.0],
                "P": [0.0, 0.0, 10.0, 10.0, 10.0],
                "F": [50.0, 50.0, 49.5, 49.5, 49.5],
            }).to_csv(path.with_suffix(".csv"), index=False)
            path.with_suffix(".json").write_text(json.dumps({
                "File_Name": "case",
                "substitutions": {"TIME_Full_Init_Time_sec": 8.0},
                "Fslack_Hz_sig": "50, AT 1s ↓ 49.5",
            }), encoding="utf-8")
            output_csv = root / "dpdf.csv"
            output_png = root / "dpdf.png"
            produce_s52511_dpdf_outputs(
                psout_paths=[str(path)],
                output_png_path=str(output_png),
                output_csv_path=str(output_csv),
                init_time_spec_key="TIME_Full_Init_Time_sec",
                pref_mw_signal_name="Pref",
                ppoc_mw_signal_name="P",
                fpoc_hz_signal_name="F",
                fslack_hz_command_spec_key="Fslack_Hz_sig",
                dpdf_characteristic_points=[(-1.0, 20.0), (1.0, -20.0)],
                pmax_mw=100.0,
                pmin_mw=-100.0,
                x86=False,
            )
            self.assertTrue(output_csv.exists())
            self.assertTrue(output_png.exists())
            self.assertEqual(len(pd.read_csv(output_csv)), 2)

    def test_mfrt_clause_handles_two_faults_and_writes_one_summary_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "mfrt.psout"
            path.write_bytes(b"cache marker")
            pd.DataFrame({
                "time": [8.0, 9.0, 9.5, 10.0, 11.0, 11.5, 12.0, 13.0],
                "Vpoc": [1.0, 1.0, 0.6, 1.0, 1.0, 0.8, 1.0, 1.0],
            }).to_csv(path.with_suffix(".csv"), index=False)
            path.with_suffix(".json").write_text(json.dumps({
                "File_Name": "mfrt",
                "substitutions": {"TIME_Full_Init_Time_sec": 8.0},
                "Fault_Timing_Signal_sig": "0, AT 1s ↑ 1, AT 2s ↓ 0, AT 3s ↑ 1, AT 4s ↓ 0",
                "Fault_Type_sig": "0, AT 1s ↑ 7, AT 2s ↓ 0, AT 3s ↑ 4, AT 4s ↓ 0",
            }), encoding="utf-8")
            output = root / "mfrt.csv"
            result = produce_s5255_mfrt_outputs(
                psout_paths=[str(path)],
                output_csv_path=str(output),
                init_time_spec_key="TIME_Full_Init_Time_sec",
                disturbance_command_spec_key="Fault_Timing_Signal_sig",
                fault_type_command_spec_key="Fault_Type_sig",
                vpoc_signal_name="Vpoc",
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(result.iloc[0]["Number of 3 Phase Faults"], 1)
            self.assertTrue(output.exists())

    def test_declarative_analysis_runner_discovers_and_dispatches_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_root = root / "results"
            input_root.mkdir()
            result_path = input_root / "case.psout"
            result_path.write_bytes(b"fixture")
            result_path.with_suffix(".json").write_text(json.dumps({"File_Name": "case"}), encoding="utf-8")
            calls = []

            def handler(psout_paths, output_csv_path):
                calls.append(list(psout_paths))
                Path(output_csv_path).write_text("ok\n", encoding="utf-8")

            status = run_analysis_pscad(
                ANALYSIS_TO_RUN=["Synthetic"],
                ANALYSIS_JOBS=[{
                    "name": "Synthetic",
                    "handler": "synthetic",
                    "inputs": [{"root": "CSR", "pattern": "**/*"}],
                    "options": {"output_csv_path": "synthetic.csv"},
                }],
                INPUT_DIRS={"CSR": str(input_root)},
                OUTPUTS_DIR=str(root / "analysis"),
                registry={"synthetic": handler},
                continue_on_error=False,
            )
            self.assertEqual(status[0]["status"], "completed")
            self.assertEqual(calls, [[str(result_path)]])
            self.assertTrue((root / "analysis" / "synthetic.csv").exists())

    def test_pscad_replotter_pairs_sidecar_and_trims_initialisation(self):
        with tempfile.TemporaryDirectory() as input_directory, tempfile.TemporaryDirectory() as output_directory:
            category = Path(input_directory) / "CSR Test"
            category.mkdir()
            path = category / "case.psout"
            path.write_bytes(b"cache marker")
            pd.DataFrame({"time": [8.0, 9.0], "P": [1.0, 2.0]}).to_csv(
                path.with_suffix(".csv"), index=False
            )
            path.with_suffix(".json").write_text(json.dumps({
                "File_Name": "case",
                "substitutions": {"TIME_Full_Init_Time_sec": 8.0},
            }), encoding="utf-8")
            plotter = _RecordingPlotter()
            outputs = replot_pscad(
                ".psout",
                plotter,
                input_directory,
                output_directory,
                x86=False,
            )
            self.assertEqual(len(outputs), 1)
            self.assertEqual(plotter.frames[0][0].index.tolist(), [0.0, 1.0])
            self.assertTrue((Path(output_directory) / "CSR Test" / "case.png").exists())


if __name__ == "__main__":
    unittest.main()
