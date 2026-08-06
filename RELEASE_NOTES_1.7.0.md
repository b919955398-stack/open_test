# Release 1.7.0 — dispatched-case cache and transparent run progress

## Main change

PSS/E studies now use a two-stage lifecycle:

1. Resolve the effective initial P/Q/V, grid fault level, X/R and infinite-grid state for every selected SPEC row.
2. Group rows with identical initial operating conditions into a Dispatch Key.
3. Load and dispatch the source SAV once for each unique key, then save one solved `dispatch_<key>.sav`.
4. Load the matching dispatched SAV directly for every dynamic scenario, without repeating the P/Q/V dispatch loop.

For example, 235 dynamic tests with 12 unique initial conditions now perform 12 load-flow dispatches instead of 235. PSS/E remains sequential and uses one simulation session at a time; this release does not add multi-process licence usage.

## Cache safety

- Cache namespaces are fingerprinted from the source SAV, project definitions, effective static configuration and `project_hooks.py`.
- Changing the source model automatically creates a new namespace; stale dispatched cases are not reused.
- Dispatch Keys always include effective P, Q, V, fault level, X/R and infinite-grid state.
- Likely inverter-count, temperature, tap-setting and initial control-mode columns are detected automatically.
- Project-specific static inputs can be added explicitly through `DISPATCH_KEY_COLUMNS`.
- `before_dispatch` and `after_dispatch` are the supported hooks for changes that must be saved into the dispatched SAV.
- SAV creation and manifest updates are published atomically; incomplete temporary SAVs are never treated as cache hits.

## Console progress

The new plain-text reporter deliberately uses no terminal colours or ANSI sequences. With `RUN_PROGRESS_LEVEL = "commands"`, it shows:

- selected SPEC scenario/category counts;
- the complete Dispatch Plan before any dispatch starts;
- cache hits, builds, failures and elapsed time;
- the key SPEC fields for every scenario;
- source/dispatched SAV loading and dynamic initialisation;
- every `RUN t1 -> t2` interval;
- every compiled fault, grid-strength, model, transformer, load and TOV command;
- study/plot success or failure and per-case elapsed time.

Set `RUN_PROGRESS_LEVEL` to `cases` for concise case-level status or `quiet` to suppress run progress. Set `SPEC_FIELDS_TO_PRINT = ["*"]` to show every populated SPEC field.

## Files and switches

- New core modules: `src/psse_open/dispatch.py` and `src/psse_open/progress.py`.
- New master switches: `USE_DISPATCH_CACHE`, `REBUILD_DISPATCH_CACHE`, `VERIFY_DISPATCH_CACHE_HASHES`, `DISPATCH_CACHE_DIR`, `DISPATCH_KEY_COLUMNS`, `AUTO_DISPATCH_KEY_COLUMNS`, `RUN_PROGRESS_LEVEL`, `PRINT_CASE_SPEC` and `SPEC_FIELDS_TO_PRINT`.
- `run_status.json` now records each scenario's Dispatch Key, cache status, dispatched SAV and elapsed time.
- Immediate per-case OUT conversion and plotting are unchanged.

## Validation

- All Python sources compile successfully.
- 52 offline unit tests pass.
- Synthetic engine regression confirms two scenarios with one initial state dispatch once, then load the same solved SAV twice.
- A second synthetic run confirms zero new dispatches and two cache hits.
- The real CSR `MFRT` sheet reduces 5 selected dynamic scenarios to one Dispatch Key and four reuses.
- Model-file modification regression confirms the old cache namespace is not reused.
- Inverter-count, temperature and tap-ratio regression confirms unsafe initial-state merging is prevented.
- Console regression confirms command output contains stable plain-text prefixes and no ANSI escape sequences.

Real PSS/E validation still requires a Windows/PSS/E 34 machine with the accepted Heywood SAV/DYR and OEM DLLs. Compare one dispatched SAV and representative flatrun/fault/MFRT results with the company runner before using the cache for issued studies.
