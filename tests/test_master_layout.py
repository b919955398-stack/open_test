import ast
import unittest
from pathlib import Path


class MasterLayoutTests(unittest.TestCase):
    def test_project_master_retains_all_workflow_sections(self):
        path = Path(__file__).resolve().parents[1] / "001 smib studies" / "4_run_psse_master_native.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        assigned = {
            target.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        self.assertTrue({
            "RUN_STUDIES",
            "PLOT_RESULTS",
            "KEEP_CSV_RESULTS",
            "SAVE_RUN_MANIFESTS",
            "KEEP_RUNTIME_FILES",
            "KEEP_RESULT_DYR",
            "KEEP_INITIALISED_SAV",
            "USE_DISPATCH_CACHE",
            "REBUILD_DISPATCH_CACHE",
            "DISPATCH_CACHE_DIR",
            "DISPATCH_KEY_COLUMNS",
            "AUTO_DISPATCH_KEY_COLUMNS",
            "RUN_PROGRESS_LEVEL",
            "PRINT_CASE_SPEC",
            "SPEC_FIELDS_TO_PRINT",
            "RUN_ANALYSIS",
            "REPLOT_PSSE",
            "CREATE_APPENDIX",
            "CREATE_REPORT_TABLES",
            "ANALYSIS_TO_RUN",
            "SPEC_OPTIONS",
        }.issubset(assigned))
        self.assertNotIn("from heywoodbess", source)
        self.assertIn("from hbess_open.analysis.run_analysis_psse", source)
        self.assertIn("from hbess_open.appendices.create_appendix", source)
        self.assertIn("load_spec_options(SPEC_OPTIONS)", source)

    def test_only_src_contains_runtime_packages(self):
        root = Path(__file__).resolve().parents[1]
        self.assertFalse((root / "hbess_open").exists())
        self.assertFalse((root / "psse_open").exists())
        self.assertTrue((root / "src" / "hbess_open").is_dir())
        self.assertTrue((root / "src" / "psse_open").is_dir())

    def test_pscad_master_is_a_complete_postprocessing_framework(self):
        path = Path(__file__).resolve().parents[1] / "001 smib studies" / "2_run_pscad_master_native.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        assigned = {
            target.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        self.assertTrue({
            "PREPARE_PSCAD_SPEC",
            "RUN_STUDIES",
            "USE_VSLACK_CACHE",
            "CALC_TOV_SHUNT_VAR",
            "RUN_ANALYSIS",
            "REPLOT_PSCAD",
            "CREATE_APPENDIX",
            "CREATE_REPORT_TABLES",
            "ANALYSIS_TO_RUN",
            "PSCAD_ANALYSIS_JOBS",
            "SPEC_OPTIONS",
        }.issubset(assigned))
        self.assertIn("from hbess_open.analysis.run_analysis_pscad", source)
        self.assertIn("from hbess_open.initialisation import prepare_pscad_spec", source)
        self.assertIn("from hbess_open.studyrunners.pscad_study_runner", source)
        self.assertNotIn("from pallet", source)
        self.assertNotIn("import mhi.pscad", source)

    def test_runtime_source_has_no_private_dependency_imports(self):
        source_root = Path(__file__).resolve().parents[1] / "src"
        source = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in source_root.rglob("*.py")
        )
        self.assertNotIn("from pallet", source)
        self.assertNotIn("import pallet", source)
        self.assertNotIn("from gridlink", source)
        self.assertNotIn("from heywoodbess", source)


if __name__ == "__main__":
    unittest.main()
