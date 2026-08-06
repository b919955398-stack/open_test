from __future__ import annotations

import json
import sys
from typing import Any, Dict, Iterable, Optional


LEVELS = {"quiet": 0, "cases": 1, "commands": 2}

LABELS = {
    "heading": "BATCH",
    "dispatch": "DISPATCH",
    "load": "LOAD",
    "command": "COMMAND",
    "success": "OK",
    "failure": "FAILED",
    "spec": "SPEC",
    "warning": "WARNING",
}


def _json_default(value: Any):
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    return str(value)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value == ""
    if type(value).__name__ in {"NAType", "NaTType"}:
        return True
    try:
        return bool(value != value)
    except Exception:
        return False


def _display(value: Any) -> str:
    if isinstance(value, float):
        return "{:.12g}".format(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default)
    return str(value)


class ConsoleReporter:
    """Small plain-text console reporter shared by the runner and engine."""

    def __init__(
        self,
        level: str = "cases",
        print_case_spec: bool = True,
        spec_fields: Optional[Iterable[str]] = None,
        stream=None,
    ):
        normalised = str(level).strip().lower()
        if normalised not in LEVELS:
            raise ValueError("progress level must be quiet, cases or commands; got {!r}".format(level))
        self.level = normalised
        self.print_case_spec = bool(print_case_spec)
        self.spec_fields = None if spec_fields is None else [str(item) for item in spec_fields]
        self.stream = stream or sys.stdout

    @classmethod
    def from_config(cls, config) -> "ConsoleReporter":
        settings = config.section("progress")
        return cls(
            level=settings.get("level", "cases"),
            print_case_spec=settings.get("print_case_spec", True),
            spec_fields=settings.get("spec_fields"),
        )

    def enabled(self, minimum: str = "cases") -> bool:
        return LEVELS[self.level] >= LEVELS[minimum]

    def emit(self, message: str, style: Optional[str] = None, minimum: str = "cases") -> None:
        if not self.enabled(minimum):
            return
        label = LABELS.get(str(style), str(style).upper()) if style else None
        prefix = "[{}] ".format(label) if label else ""
        self.stream.write(prefix + str(message) + "\n")
        self.stream.flush()

    def case_spec(self, values: Dict[str, Any], prefix: str = "SPEC") -> None:
        if not self.print_case_spec or not self.enabled("commands"):
            return
        if self.spec_fields is None or self.spec_fields == ["*"]:
            fields = [str(key) for key, value in values.items() if not _is_empty(value)]
        else:
            fields = [field for field in self.spec_fields if field in values and not _is_empty(values[field])]
        rendered = ["{}={}".format(field, _display(values[field])) for field in fields]
        self.emit("{} | {}".format(prefix, " | ".join(rendered) if rendered else "(no populated fields)"), "spec", "commands")

    def command(self, prefix: str, action: str, details: Optional[Dict[str, Any]] = None) -> None:
        message = "{} {}".format(prefix, action)
        if details:
            message += " | " + json.dumps(
                details, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default
            )
        self.emit(message, "command", "commands")
