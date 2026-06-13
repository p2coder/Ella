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
