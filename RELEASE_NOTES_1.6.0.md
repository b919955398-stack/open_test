# Release 1.6.0

## Added

- `001 smib studies/2_run_pscad_master_native.py` with the same chaptered
  structure as the PSS/E master: clauses, paths, SPEC options, studies,
  analysis, replot, appendix, report tables and one main entry point.
- Public `mhi.psout`-based binary PSOUT adapter plus same-stem pickle/CSV cache
  support and format-neutral result helpers.
- Declarative PSCAD analysis jobs and a built-in registry of 13 clause handlers.
- PSCAD implementations for ORT, MFRT, phase health, protection trip and
  maximum fault current.
- Generic PSCAD replot entry point that pairs each result with its JSON sidecar.
- Optional `requirements-pscad.txt` for machines that need binary PSOUT access.

## Refactored

- Existing dP/df, CUO, Vdroop, disturbance, diq/dV, ride-through,
  rise/settle/recovery and active-power-reduction clauses now accept PSCAD
  `.psout/.pkl/.csv` results instead of raising a PSS/E-only error.
- File discovery, grouping, sorting, handler selection and output resolution
  moved out of the master and into `src/hbess_open/analysis/run_analysis_pscad.py`.
- No runtime source imports private Pallet, an installed GridLink package or the
  old editable `heywoodbess` package.

## Deliberately deferred

- PSCAD launch, project loading, model parameter mutation, volley scheduling,
  run callbacks and immediate study plotting are not implemented in this
  release. `RUN_STUDIES` remains `False` and the source runner is a clear stub.
- Real Heywood sheet selections, result folder names, signal/channel mappings,
  characteristic points and analysis jobs remain blank in the PSCAD master
  pending project-specific instructions.

## Validation

- 41 offline unit tests pass.
- Every Python source compiles.
- PSOUT conversion was tested against an official-API-shaped fake object;
  PSCAD dP/df, MFRT and replot flows were tested from same-stem CSV caches.
- A real binary project PSOUT still requires validation on the PSCAD machine
  with the matching official `mhi.psout` package.
