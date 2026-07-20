from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable


class ConfigurationError(ValueError):
    pass


class ProjectConfig:
    """Thin validated wrapper around a deliberately transparent JSON file."""

    def __init__(self, path: str, data: Dict[str, Any]):
        self.path = Path(path).resolve()
        self.data = data

    @classmethod
    def load(cls, path: str) -> "ProjectConfig":
        with open(path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        config = cls(path, data)
        config.validate()
        return config

    @property
    def base_dir(self) -> Path:
        configured = self.data.get("project_root", ".")
        configured = os.path.expandvars(os.path.expanduser(str(configured)))
        value = Path(configured)
        if not value.is_absolute():
            value = self.path.parent / value
        return value.resolve()

    def resolve(self, value: str) -> Path:
        expanded = Path(os.path.expandvars(os.path.expanduser(str(value))))
        return expanded if expanded.is_absolute() else (self.base_dir / expanded).resolve()

    def section(self, name: str) -> Dict[str, Any]:
        value = self.data.get(name, {})
        if not isinstance(value, dict):
            raise ConfigurationError("Configuration section {!r} must be an object".format(name))
        return value

    def require(self, dotted_name: str) -> Any:
        current: Any = self.data
        for part in dotted_name.split("."):
            if not isinstance(current, dict) or part not in current:
                raise ConfigurationError("Missing required configuration: {}".format(dotted_name))
            current = current[part]
        return current

    def validate(self) -> None:
        required: Iterable[str] = (
            "files.sav",
            "files.dyr",
            "system.poc_bus",
            "system.infinite_bus",
            "system.grid_branch.from_bus",
            "system.grid_branch.to_bus",
            "system.grid_branch.id",
            "system.infinite_machine.id",
        )
        missing = []
        for name in required:
            try:
                self.require(name)
            except ConfigurationError:
                missing.append(name)
        if missing:
            raise ConfigurationError("Missing required configuration keys: {}".format(", ".join(missing)))
