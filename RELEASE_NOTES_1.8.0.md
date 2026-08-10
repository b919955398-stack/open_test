# Release 1.8.0 — TOV reliability and first-stage runtime improvements

## TOV fixes

- Every dynamic case now receives a case- and profile-specific eight-character
  PLBVFU1 playback stem. This prevents a shared PSS/E runtime directory from
  reusing another case's external playback file and producing a flat TOV run.
- CSR-style Vslack TOV profiles and structured `TOV_MVAr`/capacitance shunts
  are both compiled into executable disturbances.
- A TOV plan with no non-flat playback or shunt now fails before PSS/E starts.
  Completed TOV data is also checked at the POC; a flat voltage channel fails
  loudly and preserves a diagnostic CSV instead of publishing a plausible plot.

## First-stage performance work

- OUT channels are decoded directly into a DataFrame. The former temporary
  CSV write/read round trip is skipped on successful studies.
- One background plot worker overlaps plotting case N with the PSS/E run for
  case N+1, without consuming another PSS/E licence.
- Plot-only adaptive downsampling limits rendering work while retaining full
  OUT resolution and samples around all event/playback transitions.
- Result DYR files use a hard link where supported, and initialised SAV files
  are moved from staging instead of copied; both retain portable fallbacks.
- Per-stage timings are recorded in `run_status.json`.
- Complete six-file results can be resumed safely. Model files, definitions,
  hooks, compiled commands, scenario values and plotter sources participate in
  the fingerprint; changed or incomplete results rerun automatically.

## Master layout

- `4_run_psse_master_native.py` now follows the supplied company master
  structure: sheet choices, paths, workflow blocks and the final main entry
  point retain the same organization.
- Runtime, cache, output, console and performance defaults live in
  `run_psse_studies()`. The master calls it with only `spec`, `plotter`,
  `MODEL_DIR` and `RESULTS_DIR`.

## Validation

- Regression coverage verifies real CSR TOV profile compilation, missing-TOV
  rejection, structured MVAr shunts, unique playback stems, flat-result
  detection, direct OUT decoding, transition-preserving downsampling and safe
  result resume.
- Real licensed PSS/E 34 execution remains the final validation step on the
  Windows study machine.
