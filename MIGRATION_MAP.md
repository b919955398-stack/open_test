# Private dependency migration map

| Original dependency/capability | Native source implementation |
|---|---|
| `pallet.psse.Out.Out(...).to_df()` | `hbess_open.io.psse_out.PsseOut` / `out_to_df` |
| `pallet.pscad.Psout(...).to_df()` | `hbess_open.io.pscad_out.PscadOut` / official `mhi.psout.File` |
| `pallet.utils.alternative_dyntools.out_to_df` | Adjacent CSV reader with optional Siemens `dyntools` fallback |
| `pallet.dsl.ParsedDslSignal` | `hbess_open.io.signal_dsl.ParsedSignal` |
| `pallet.specs.load_specs_*` | `hbess_open.open_psse.specs` |
| `pallet.utils.time_utils.now_str` | `hbess_open.open_psse.specs.now_str` |
| `gridlink.analysis.settling_analysis` | `hbess_open.analysis.gridlink.settling_analysis` |
| GridLink characteristic/rise-settle/disturbance/box plots | `hbess_open.analysis.gridlink.*` |
| `gridlink.utils.spec_utils` | `hbess_open.analysis.gridlink.spec_utils` |
| `PscadPallet.add_vslacks_to_spec` / `utils.vslack` cache | `hbess_open.initialisation.prepare_pscad_spec` |
| `PscadPallet.add_tov_shunt_size_to_spec` / pandapower TOV solve | `hbess_open.initialisation.calculate_tov_shunt_mvar` |
| PSS/E Initialiser/Vslack pass | `hbess_open.studyrunners.psse_study_runner.get_vslacks` |
| Pallet PSS/E simulation wrapper | `psse_open.backend.PsseBackend` + `StudyEngine` |
| Old `heywoodbess.*` package imports | Collision-free `hbess_open.*` under project `src` |
| Hard-coded `run_analysis_pscad.py` branches | Declarative `hbess_open.analysis.run_analysis_pscad` registry/jobs |

PSS/E execution, PSCAD electrical SPEC initialisation and PSCAD
post-processing are included. PSCAD simulation launch/execution, WAN
DLL/cache/results and unrelated legacy utilities are not copied into the
runtime package.
