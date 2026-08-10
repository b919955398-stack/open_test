# Release 1.7.2 — dispatch signal-profile compatibility

## Correction

- Accepts HY signal profiles in steady-state dispatch columns such as
  `Ppoc_MW_sig`, for example `285, AT 5s ↓ 142.5`.
- Uses only the time-zero value (`285 MW` in the example) when building the
  Dispatch Key and solving the initial P/Q/V operating point.
- Leaves later profile points to the existing compiled `PSSE Commands`, so
  reference-step tests are neither omitted nor applied twice.
- Applies the same time-zero parsing consistently to P, Q, POC voltage, fault
  level and X/R inputs used by the native backend.

## Root cause

The v1.7.1 cache signature and native backend called `float()` directly on
dispatch fields.  Numeric scenarios passed, but Pref rows containing the full
human-readable signal profile failed before the first dispatched SAV was
created.

## Validation

- The exact failing Pref profile is covered by unit tests.
- Numeric `285.0` and profiled `285, AT ...` scenarios are confirmed to share
  one Dispatch Key.
- The complete offline suite passes: 56 tests.
- Real PSS/E validation remains required on the project Windows/PSS/E 34
  environment.
