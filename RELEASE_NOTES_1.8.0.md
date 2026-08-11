# Release 1.8.0 — TOV reliability and first-stage runtime improvements

## TOV fixes

- Every dynamic case now receives a case- and profile-specific eight-character
  PLBVFU1 playback stem. This prevents a shared PSS/E runtime directory from
  reusing another case's external playback file and producing a flat TOV run.
- Cases with a parsed playback profile retain the exact generated PLB in the
  result folder as `<File_Name>.plb`. Cases without playback retain no PLB.
- CSR-style Vslack TOV profiles and structured `TOV_MVAr`/capacitance shunts
  are both compiled into executable disturbances.
- SPEC `CHANGE FIXED_SHUNT '<name>' MVAR TO <value> AT <time>s` and
  `TRIP FIXED_SHUNT '<name>' AT <time>s` commands compile into native events;
  the backend resolves `<name>` through project `system.fixed_shunts` and uses
  the public PSS/E fixed-shunt change API.
- Vslack playback and fixed-shunt commands are independent: either, both or
  neither method runs exactly according to the SPEC, without a master selector.
- TOV results always follow the normal plotting path, including flat traces.
  The runner does not apply a waveform-range correctness gate; the engineer
  reviews the generated PNG/PDF and decides whether the response is valid.

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
- Complete six-file core results can be resumed safely. Playback cases also
  require their retained PLB. Model files, definitions, hooks, compiled
  commands, scenario values and plotter sources participate in the fingerprint;
  changed playback profiles or incomplete results rerun automatically.

## Master layout

- `4_run_psse_master_native.py` now follows the supplied company master
  structure: sheet choices, paths, workflow blocks and the final main entry
  point retain the same organization.
- Runtime, cache, output, console and performance defaults live in
  `run_psse_studies()`. The master calls it with only `spec`, `plotter`,
  `MODEL_DIR` and `RESULTS_DIR`.

## Validation

- Regression coverage verifies real CSR TOV profile compilation, structured
  MVAr shunts, unique playback stems, flat-result plotting without automatic
  waveform judgement, direct OUT decoding, transition-preserving downsampling
  and safe result resume.
- Real licensed PSS/E 34 execution remains the final validation step on the
  Windows study machine.
