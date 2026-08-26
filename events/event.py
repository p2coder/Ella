from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .signal import serialize_timestamp, utc_now
from .stage import EVENT_CANDIDATE_STAGE, STANDARDIZED_EVENT_STAGE, EventStage


@dataclass(frozen=True, slots=True)
class EventCandidate:
    trace_id: str
    source: str
    payload: dict[str, Any]
    event_type: str
    timestamp: datetime = field(default_factory=utc_now)
    stage: EventStage = EVENT_CANDIDATE_STAGE
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "source": self.source,
            "timestamp": serialize_timestamp(self.timestamp),
            "payload": self.payload,
            "event_type": self.event_type,
            "stage": self.stage.name,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class StandardizedEvent:
    trace_id: str
    source: str
    payload: dict[str, Any]
    event_type: str
    timestamp: datetime = field(default_factory=utc_now)
    stage: EventStage = STANDARDIZED_EVENT_STAGE
    confidence: float | None = None
    priority: float | None = None
    target_task_id: str | None = None
    caused_by_task_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "source": self.source,
            "timestamp": serialize_timestamp(self.timestamp),
            "payload": self.payload,
            "event_type": self.event_type,
            "stage": self.stage.name,
            "confidence": self.confidence,
            "priority": self.priority,
            "target_task_id": self.target_task_id,
            "caused_by_task_id": self.caused_by_task_id,
            "metadata": self.metadata,
        }


Event = StandardizedEvent
