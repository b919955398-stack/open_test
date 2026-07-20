from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Scenario:
    sheet: str
    row_number: int
    file_name: str
    enabled: bool
    values: Dict[str, Any]

    def get(self, name: str, default: Any = None) -> Any:
        value = self.values.get(name, default)
        return default if value is None or value == "" else value

    @property
    def category(self) -> str:
        return str(self.get("Category", self.get("TEST_TYPE", self.sheet)))

    @property
    def end_time(self) -> float:
        value = self.get("Post_Init_Duration_s", self.get("rundur", 10.0))
        return float(value)


@dataclass(order=True)
class Event:
    time: float
    order: int
    kind: str = field(compare=False)
    parameters: Dict[str, Any] = field(default_factory=dict, compare=False)
    source: str = field(default="structured columns", compare=False)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "time": self.time,
            "kind": self.kind,
            "parameters": self.parameters,
            "source": self.source,
        }


@dataclass
class PlaybackPoint:
    time: float
    voltage_pu: Optional[float] = None
    frequency_hz: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "time": self.time,
            "voltage_pu": self.voltage_pu,
            "frequency_hz": self.frequency_hz,
        }


@dataclass
class StudyPlan:
    scenario: Scenario
    events: List[Event]
    playback: List[PlaybackPoint] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "sheet": self.scenario.sheet,
            "row_number": self.scenario.row_number,
            "file_name": self.scenario.file_name,
            "category": self.scenario.category,
            "end_time": self.scenario.end_time,
            "events": [event.as_dict() for event in self.events],
            "playback": [point.as_dict() for point in self.playback],
            "warnings": self.warnings,
        }
