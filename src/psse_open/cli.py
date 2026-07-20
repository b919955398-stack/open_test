from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .config import ConfigurationError, ProjectConfig
from .definitions import load_or_build_project_config
from .engine import StudyEngine, create_plans, write_plan
from .plotting import load_plot_config, plot_csv
from .spec import SpecError, SpecWorkbook


def _patterns(value: Optional[str]) -> Optional[List[str]]:
    return [item.strip() for item in value.split(",") if item.strip()] if value else None


def _load_scenarios(args):
    workbook = SpecWorkbook(args.spec)
    scenarios = workbook.scenarios(_patterns(args.sheets), not args.include_disabled, args.filter, args.limit)
    warnings = workbook.validate_cached_values(scenarios)
    return workbook, scenarios, warnings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Transparent SPEC-driven PSS/E automation")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_spec_options(command):
        command.add_argument("--spec", required=True, help="HY or open DMAT .xlsx workbook")
        command.add_argument("--sheets", help="Comma-separated sheet names/globs, e.g. 5255_BalFaults,52513_*")
        command.add_argument("--filter", help="Substring filter against sheet and File_Name")
        command.add_argument("--limit", type=int)
        command.add_argument("--include-disabled", action="store_true")

    validate = sub.add_parser("validate", help="Validate and summarise a workbook without PSS/E")
    add_spec_options(validate)
    plan = sub.add_parser("plan", help="Compile SPEC rows to explicit events without PSS/E")
    add_spec_options(plan)
    plan.add_argument("--output", default="study_plan.json")
    run = sub.add_parser("run", help="Run selected scenarios")
    add_spec_options(run)
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--model-dir", help="Auto-build config from SAV/DYR/savdef/initdef/chandef")
    source.add_argument("--config", help="Load a complete standalone JSON config")
    run.add_argument("--plan-output", default="study_plan.json")

    plot = sub.add_parser("plot", help="Plot one CSV using a transparent JSON panel definition")
    plot.add_argument("--csv", required=True)
    plot.add_argument("--config", required=True)
    plot.add_argument("--output", required=True)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plot":
            target = plot_csv(args.csv, args.output, load_plot_config(args.config))
            print(target)
            return 0
        workbook, scenarios, warnings = _load_scenarios(args)
        if args.command == "validate":
            print(json.dumps({
                "format": workbook.format, "spec": str(workbook.path), "study_sheets": workbook.sheet_names,
                "selected_scenarios": len(scenarios), "warnings": warnings,
            }, indent=2, ensure_ascii=False))
            return 1 if warnings else 0
        plans = create_plans(scenarios)
        for warning in warnings:
            print("WARNING: " + warning, file=sys.stderr)
        target = write_plan(plans, args.output if args.command == "plan" else args.plan_output)
        print("Compiled {} scenarios to {}".format(len(plans), target))
        if args.command == "plan":
            return 0
        config = load_or_build_project_config(args.model_dir) if args.model_dir else ProjectConfig.load(args.config)
        results = StudyEngine(config).run(plans)
        failed = sum(1 for result in results if result["status"] == "failed")
        print("Completed {}; failed {}".format(len(results) - failed, failed))
        return 1 if failed else 0
    except (ConfigurationError, SpecError, ValueError, RuntimeError, FileNotFoundError) as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
