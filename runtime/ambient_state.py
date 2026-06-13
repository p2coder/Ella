from dataclasses import dataclass, field

from events import StandardizedEvent


@dataclass(slots=True)
class AmbientState:
    _latest_by_event_type: dict[str, StandardizedEvent] = field(default_factory=dict)

    def update(self, event: StandardizedEvent) -> None:
        self._latest_by_event_type[event.event_type] = event

    def latest(self, event_type: str) -> StandardizedEvent | None:
        return self._latest_by_event_type.get(event_type)

    def to_dict(self) -> dict[str, dict]:
        return {
            event_type: event.to_dict()
            for event_type, event in self._latest_by_event_type.items()
        }
