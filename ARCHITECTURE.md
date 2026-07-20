# Architecture

| Layer | Source path | Responsibility |
|---|---|---|
| Project master | `001 smib studies/4_run_psse_master_native.py` | Clause lists, paths, switches and orchestration only |
| SPEC adapter | `src/hbess_open/open_psse/specs.py` | Multi-workbook/sheet loading and timestamps |
| Heywood runner | `src/hbess_open/studyrunners/psse_study_runner.py` | Vslack pre-pass and StudyEngine adapter |
| PSS/E compiler | `src/psse_open/commands.py` | Recognised SPEC command strings → typed events |
| Native backend | `src/psse_open/backend.py` | Direct public `psspy` calls |
| Engine | `src/psse_open/engine.py` | Per-case lifecycle and OUT/CSV/JSON results |
| Pallet replacement | `src/hbess_open/io/` | Signal DSL and OUT/CSV reader |
| GridLink replacement | `src/hbess_open/analysis/gridlink/` | Step metrics and analysis plot primitives |
| Clause analysis | `src/hbess_open/analysis/clause_analysis/` | S5.2.5 clause calculations |
| Study plotting/replot | `src/hbess_open/plotting/` | Heywood plotter and existing-result replay |
| Appendix | `src/hbess_open/appendices/` | SPEC routing and XeLaTeX PDF generation |
| Report tables | `src/hbess_open/report_tables/` | Column-map-driven CSV generation |

## Dependency direction

```text
master
  → hbess_open workflow modules
      → psse_open engine (only for simulation)
      → hbess_open io/analysis primitives (for post-processing)
          → pandas / numpy / matplotlib
```

There is no runtime import from `pallet`, installed `gridlink`, or old `heywoodbess`.

## Case lifecycle

1. Load selected SPEC rows and resolve `$VSLACK` where required.
2. Compile a reviewable `study_plan.json`.
3. Copy model inputs into an isolated work directory.
4. Load SAV, configure grid, dispatch P/Q/V, convert and initialise dynamics.
5. Run ordered events through the public `psspy` API.
6. Write `<File_Name>.out`, `.csv` and `.json` in the category folder.
7. Run the Heywood plotter.
8. Optionally analyse, replot, create appendices and create report tables from the same results tree.

PSS/E is imported only when `StudyEngine` is constructed or when an old OUT-only directory must be read. SPEC checks and CSV-based post-processing run without PSS/E.
