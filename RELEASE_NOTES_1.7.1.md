# Release 1.7.1 — full GitHub delivery and native PSS/E console output

## Corrections

- Publishes the complete v1.7 dispatched-case cache implementation instead of only the master sheet selection.
- Preserves the current DMAT sheet selection from the repository master.
- Adds `PSSE_OUTPUT_MODE = "console" | "files" | "quiet"`.
- Defaults the project master to `console`, so PSS/E load-flow iterations, tap/machine changes, initial-condition checks, channels and dynamic RUN progress remain visible in PowerShell.
- Retains the plain-text SPEC, Dispatch Key, cache hit/build and event-command reporter without ANSI colours.
- Resolves the modern Python dependency conflict between pandas and openpyxl while retaining the legacy Python pins.

## Validation

- Python source compilation passes.
- Offline unit tests cover dispatch reuse, cache invalidation, progress output and native PSS/E stream routing.
- Real PSS/E validation remains required on the project Windows/PSS/E 34 environment before issued studies.
