"""Heywood-only extension points.

Keep project/model-specific operations here. The engine remains reusable and
transparent. Return True from handle_event when a custom event is handled.
"""


def before_case(backend, scenario, work_dir):
    pass


def after_dispatch(backend, scenario, work_dir):
    """Add site-specific PPC mode or plant initialization changes here."""
    pass


def after_dynamic_initialization(backend, scenario, work_dir):
    pass


def handle_event(backend, event, scenario):
    if event.kind == "callback":
        name = event.parameters["name"]
        callback = globals().get(name)
        if callback is None:
            raise RuntimeError("Active Callback {!r} is not defined in project_hooks.py".format(name))
        callback(backend, scenario)
        return True

    return False
