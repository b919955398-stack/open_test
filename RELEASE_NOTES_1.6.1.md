# Release 1.6.1

## Restored as open source

- PSCAD `constant_vslack_pu_sig` calculation from fault level, X/R and the
  requested P/Q/V operating point.
- Functional `USE_VSLACK_CACHE`: `False` recalculates all selected rows and
  atomically rebuilds the cache; `True` reuses matches and calculates misses.
- Functional `CALC_TOV_SHUNT_VAR`: `True` calculates shunt MVAr and
  `TOV_Shunt_C_uF_sig`; `False` preserves existing values and can fill missing
  values from the cache.
- `TOV_MVAr` follows the legacy pandapower shunt convention: it is the bank
  rating at 1.0 pu, while actual injection at `U_Ov` scales with `U_Ov**2`.
- `$VSLACK` replacement in `Vslack_pu_sig`, including signal-DSL expressions.
- Compatibility reading for the legacy cache keys using `Ppoc_pu` and
  `Qpoc_pu` as well as the new explicit MW/MVAr cache format.

## Architecture

- The electrical equations live in `src/hbess_open/initialisation/`; the outer
  master contains configuration and orchestration only.
- `PREPARE_PSCAD_SPEC` can run initialisation and write one prepared CSV without
  launching PSCAD. The launch/project/volley runner remains deliberately
  deferred.
- Cache matching no longer uses a DataFrame merge, so the prepared SPEC does
  not acquire `_from_cache`, copied-key or index columns.
- Normal output is one summary line rather than the complete SPEC DataFrame.

## TOV selection

- If any row has `Calc_TOV=True`, only those rows are recalculated.
- If the column exists but all values are false (as in the supplied TOV
  sheets), enabling the global switch calculates rows with a positive `U_Ov`.
- Disabling the global switch never recalculates TOV values.

## Validation

- 46 offline tests pass and every Python source compiles.
- The supplied 32-row Fgrid sheet prepared without unresolved placeholders.
- The supplied 96-row TOV sheet produced MVAr and capacitance for every row.
- A final numerical comparison against the accepted Windows/Pallet cache is
  still required before issuing project studies.
