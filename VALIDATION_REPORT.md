# Validation report

Release: 1.7.2 (`src` architecture, persistent PSS/E dispatched-case cache, transparent command/native PSS/E progress and PSCAD post-processing framework)

## Completed offline checks

- Master imports every implementation from this project's `src` tree without importing PSS/E.
- Runtime source contains no imports from `pallet`, installed `gridlink`, or old `heywoodbess`.
- 56 unit tests cover definitions, channel mappings, commands, profiles, grid math, Vslack/TOV calculations, PSS/E dispatch grouping/cache/invalidation/reuse, plain-text progress, legacy/new PSCAD cache handling, collision-free layout, DSL parsing, CSV/OUT/PSOUT reading, settling metrics, PSS/E/PSCAD replot pairing and declarative PSCAD analysis dispatch.
- Synthetic result cases produced dP/df, Vdroop, rise/settle, disturbance tracking, diq/dV, Iq recovery, cumulative ride-through and active-power-reduction CSV/PNG outputs.
- CSR report-table generation was run against the supplied `HY_Spec_CSR_300.xlsx` and `column_mapping_CSR.csv`.
- All Python sources compile successfully on the validation runtime.
- A synthetic official-API-shaped PSOUT object was converted to a time-indexed dataframe, including initialisation trimming and channel-name recovery.
- PSCAD dP/df and MFRT clauses were exercised from same-stem CSV caches without Pallet or PSCAD installed.
- The supplied `52511_Fgrid_AEMO_discussion` sheet prepared 32/32 Vslack rows with no unresolved `$VSLACK` tokens or merge-helper columns.
- The supplied `5255_TOV` sheet analytically prepared 96/96 TOV rows; MVAr and uF outputs were finite and positive for the requested overvoltage cases.
- The supplied CSR `MFRT` sheet selected 5/5 PSS/E scenarios and correctly reduced them to one Dispatch Key (P=285 MW, Q=0 MVAr, V=1.06 pu, FL=3185 MVA, X/R=11.24), giving four in-batch reuses.
- Synthetic PSS/E engine tests grouped two dynamic scenarios into one Dispatch Key, executed one load-flow dispatch, loaded the saved SAV twice, then confirmed a second batch produced two cache hits and zero new dispatches.
- Numeric initial P/Q/V values and HY signal profiles with the same time-zero value produce the same Dispatch Key; the backend dispatches the time-zero value while later reference steps remain dynamic commands.
- Source-SAV modification produced a new cache namespace; differing inverter-count, temperature and tap-ratio inputs produced distinct Dispatch Keys.
- Command progress tests confirm stable `[SPEC]`/`[DISPATCH]`/`[LOAD]`/`[COMMAND]` prefixes with no ANSI escape sequences.

## External validation still required

- Real PSS/E execution needs Windows, the matching Siemens Python/PSS/E installation, licence, SAV/DYR and OEM DLLs.
- Binary PSCAD validation still needs a real project `.psout` plus the matching official `mhi.psout` package; PSCAD simulation execution is intentionally deferred.
- TOV values should be compared with the accepted project cache/Pallet output on the Windows study machine before issue; no populated TOV reference values were present in the supplied workbook.
- Appendix PDF compilation needs XeLaTeX plus the fonts/packages required by the supplied class file.
- Before issuing studies, benchmark representative steady-state, fault, playback and reference-step cases against the accepted original results.
- On the Windows/PSS/E machine, compare the first generated dispatched SAV and representative MFRT result against the company runner before enabling cache reuse for issued studies.
