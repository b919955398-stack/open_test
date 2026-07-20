from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Optional


def load_hooks(path: Optional[str]) -> Optional[ModuleType]:
    if not path:
        return None
    target = Path(path).resolve()
    spec = importlib.util.spec_from_file_location("psse_project_hooks", str(target))
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load project hooks: {}".format(target))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call_hook(module: Optional[ModuleType], name: str, *args, **kwargs):
    function = getattr(module, name, None) if module else None
    return function(*args, **kwargs) if function else None
