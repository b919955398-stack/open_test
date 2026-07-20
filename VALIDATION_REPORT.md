# Validation report

Release: 1.5.0 (`src` architecture, shared runtime and immediate per-case plotting)

## Completed offline checks

- Master imports every implementation from this project's `src` tree without importing PSS/E.
- Runtime source contains no imports from `pallet`, installed `gridlink`, or old `heywoodbess`.
- 26 unit tests cover definitions, channel mappings, commands, profiles, grid math, collision-free layout, DSL parsing, CSV/OUT reading, settling metrics and replot pairing.
- Synthetic result cases produced dP/df, Vdroop, rise/settle, disturbance tracking, diq/dV, Iq recovery, cumulative ride-through and active-power-reduction CSV/PNG outputs.
- CSR report-table generation was run against the supplied `HY_Spec_CSR_300.xlsx` and `column_mapping_CSR.csv`.
- All Python sources compile successfully on the validation runtime.

## External validation still required

- Real PSS/E execution needs Windows, the matching Siemens Python/PSS/E installation, licence, SAV/DYR and OEM DLLs.
- Appendix PDF compilation needs XeLaTeX plus the fonts/packages required by the supplied class file.
- Before issuing studies, benchmark representative steady-state, fault, playback and reference-step cases against the accepted original results.
