from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LocalTrace:
    trace_id: str
    events: list[dict[str, object]] = field(default_factory=list)

    def add_event(self, event: dict[str, object]) -> None:
        self.events.append(event)

