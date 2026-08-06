"""Reserved boundary for the future open PSCAD execution engine.

Vslack/TOV SPEC initialisation is implemented independently of PSCAD launch so
it can already be validated and used to prepare studies.
"""

from hbess_open.initialisation import prepare_pscad_spec


def prepare_pscad_studies(spec, **options):
    """Prepare the electrical initial conditions consumed by the future runner."""
    return prepare_pscad_spec(spec, **options)


def run_pscad_studies(**_options):
    """PSCAD execution is intentionally outside the current release scope."""
    raise NotImplementedError(
        "PSCAD study execution has not been implemented yet. Keep RUN_STUDIES=False; "
        "the analysis, replot, appendix and report-table stages can process existing results."
    )
