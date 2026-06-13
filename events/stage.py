from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EventStage:
    """Configurable event stage key used by the event data contracts."""

    name: str
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("event stage name must not be empty")


OBSERVATION_STAGE = EventStage(
    "observation",
    "Environment observation that may or may not become an event.",
)
EVENT_CANDIDATE_STAGE = EventStage(
    "event_candidate",
    "Potential event awaiting standardization or ambient-state handling.",
)
STANDARDIZED_EVENT_STAGE = EventStage(
    "standardized_event",
    "Standard event contract ready for later routing.",
)

DEFAULT_EVENT_STAGES = (
    OBSERVATION_STAGE,
    EVENT_CANDIDATE_STAGE,
    STANDARDIZED_EVENT_STAGE,
)


class EventStageRegistry:
    """Mutable catalog of event stage keys used to configure pipelines."""

    def __init__(self, stages: tuple[EventStage, ...] = DEFAULT_EVENT_STAGES) -> None:
        self._stages: dict[str, EventStage] = {}
        for stage in stages:
            self.register(stage)

    def register(self, stage: EventStage) -> None:
        self._stages[stage.name] = stage

    def unregister(self, stage_name: str) -> None:
        self._stages.pop(stage_name, None)

    def get(self, stage_name: str) -> EventStage | None:
        return self._stages.get(stage_name)

    def list_stages(self) -> tuple[EventStage, ...]:
        return tuple(self._stages.values())
