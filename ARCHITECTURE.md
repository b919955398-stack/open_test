# Architecture

| Layer | Source path | Responsibility |
|---|---|---|
| Project masters | `001 smib studies/4_run_psse_master_native.py`, `2_run_pscad_master_native.py` | Clause lists, paths, switches and orchestration only |
| SPEC adapter | `src/hbess_open/open_psse/specs.py` | Multi-workbook/sheet loading and timestamps |
| Grid initialisation | `src/hbess_open/initialisation/` | Open two-bus Vslack/TOV calculations and compact PSCAD cache |
| Heywood runner | `src/hbess_open/studyrunners/psse_study_runner.py` | Vslack pre-pass and StudyEngine adapter |
| PSS/E compiler | `src/psse_open/commands.py` | Recognised SPEC command strings → typed events |
| Dispatch planner/cache | `src/psse_open/dispatch.py` | Effective initial-state keys, model fingerprinting and solved SAV cache |
| Console progress | `src/psse_open/progress.py` | Plain-text SPEC, stage and command reporting |
| Native backend | `src/psse_open/backend.py` | Direct public `psspy` calls |
| Engine | `src/psse_open/engine.py` | Per-case lifecycle and OUT/CSV/JSON results |
| Result adapters | `src/hbess_open/io/` | Signal DSL, OUT/CSV and public MHI PSOUT readers |
| GridLink replacement | `src/hbess_open/analysis/gridlink/` | Step metrics and analysis plot primitives |
| Clause analysis | `src/hbess_open/analysis/clause_analysis/` | S5.2.5 clause calculations |
| PSCAD analysis dispatcher | `src/hbess_open/analysis/run_analysis_pscad.py` | Declarative result discovery, grouping and clause dispatch |
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

The PSCAD launch/execution boundary currently stops at
`src/hbess_open/studyrunners/pscad_study_runner.py`; it deliberately raises a
clear `NotImplementedError`. PSCAD SPEC initialisation is independent of that
boundary: Vslack, TOV shunt MVAr/capacitance, cache reuse and `$VSLACK`
expansion are implemented in `src/hbess_open/initialisation/`. Existing PSCAD
results can also pass through PSOUT reading, clause analysis, replot, appendix
and report-table stages.

## PSCAD initialisation flow

1. The PSCAD master loads selected rows with the common `SPEC_OPTIONS` block.
2. `prepare_pscad_spec` resolves the initial P/Q/V and Thevenin R/X for each row.
3. Vslack is read from `vslack_cache.csv` when enabled; cache misses are calculated analytically.
4. When enabled, TOV shunt MVAr is solved on the stable two-bus branch, converted to its 1.0 pu capacitor-bank rating and then to uF.
5. `$VSLACK` is expanded without retaining merge/suffix helper columns.
6. The cache is replaced atomically only after every selected row succeeds.

## PSCAD post-processing flow

1. The outer PSCAD master selects workflow switches and supplies declarative jobs.
2. `run_analysis_pscad` resolves result roots and glob selectors.
3. Each `.psout/.pkl/.csv` is paired with its same-stem JSON sidecar.
4. Optional `group_by`/`sort_by` keys are read from sidecar metadata.
5. A registered clause handler reads data through `result_to_df` and writes its CSV/PNG outputs.
6. Binary `.psout` uses official `mhi.psout`; same-stem pickle/CSV caches bypass the binary reader.

## Case lifecycle

1. Load selected SPEC rows and resolve `$VSLACK` where required.
2. Compile a reviewable `study_plan.json`.
3. Copy model inputs into an isolated work directory.
4. Resolve each row's effective initial P/Q/V/grid state and print the complete Dispatch Plan.
5. For each missing unique Dispatch Key, load the source SAV, configure grid, dispatch P/Q/V and atomically publish one solved SAV.
6. For every dynamic scenario, load its solved dispatched SAV without repeating load-flow dispatch.
7. Convert and initialise dynamics, then run ordered events through the public `psspy` API while reporting each time interval and command.
8. Write `<File_Name>.out`, `.csv` and `.json` in the category folder.
9. Run the Heywood plotter immediately before the next scenario starts.
10. Optionally analyse, replot, create appendices and create report tables from the same results tree.

The dispatch namespace fingerprint covers the source SAV, definition files,
effective static configuration and project hooks. A scenario key covers the
effective P/Q/V, fault level, X/R and infinite-grid state plus configured or
automatically detected initial-state columns. Dynamic events, output settings
and `File_Name` are intentionally excluded so cases with the same initial
operating point can share one solved SAV.

PSS/E is imported only when `StudyEngine` is constructed or when an old OUT-only directory must be read. SPEC checks and CSV-based post-processing run without PSS/E.
