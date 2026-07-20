# Private dependency migration map

| Original dependency/capability | Native source implementation |
|---|---|
| `pallet.psse.Out.Out(...).to_df()` | `hbess_open.io.psse_out.PsseOut` / `out_to_df` |
| `pallet.utils.alternative_dyntools.out_to_df` | Adjacent CSV reader with optional Siemens `dyntools` fallback |
| `pallet.dsl.ParsedDslSignal` | `hbess_open.io.signal_dsl.ParsedSignal` |
| `pallet.specs.load_specs_*` | `hbess_open.open_psse.specs` |
| `pallet.utils.time_utils.now_str` | `hbess_open.open_psse.specs.now_str` |
| `gridlink.analysis.settling_analysis` | `hbess_open.analysis.gridlink.settling_analysis` |
| GridLink characteristic/rise-settle/disturbance/box plots | `hbess_open.analysis.gridlink.*` |
| `gridlink.utils.spec_utils` | `hbess_open.analysis.gridlink.spec_utils` |
| Pallet Initialiser/Vslack pass | `hbess_open.studyrunners.psse_study_runner.get_vslacks` |
| Pallet PSS/E simulation wrapper | `psse_open.backend.PsseBackend` + `StudyEngine` |
| Old `heywoodbess.*` package imports | Collision-free `hbess_open.*` under project `src` |

Only the PSS/E path requested by the project is included. PSCAD, WAN DLL/cache/results and unrelated legacy utilities from the archives are not copied into the runtime package.
