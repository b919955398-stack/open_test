"""Compatibility entry point for the former project Vslack helper."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from hbess_open.initialisation.pscad_spec import prepare_pscad_spec


def calc_vslacks_with_caching(
    spec: pd.DataFrame,
    use_cache: bool,
    spec_path: str,
    vbase_kv: float,
    fbase_hz: float,
    calc_tov_shunt_var: bool = True,
    system_base_mva: float = 100.0,
    pbase_mw: Optional[float] = None,
    qbase_mvar: Optional[float] = None,
) -> pd.DataFrame:
    """Compatibility wrapper with the original helper's argument order.

    ``spec_path`` may be either an XLSX path or its containing directory.  New
    code should call :func:`hbess_open.initialisation.prepare_pscad_spec`
    directly so that the cache path and TOV switch are explicit.
    """
    source = Path(spec_path).expanduser()
    folder = source if source.suffix == "" else source.parent
    return prepare_pscad_spec(
        spec,
        use_vslack_cache=use_cache,
        calc_tov_shunt_var=calc_tov_shunt_var,
        cache_path=str(folder / "vslack_cache.csv"),
        vbase_kv=vbase_kv,
        fbase_hz=fbase_hz,
        system_base_mva=system_base_mva,
        pbase_mw=pbase_mw,
        qbase_mvar=qbase_mvar,
    )
