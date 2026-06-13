from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .signal import serialize_timestamp, utc_now
from .stage import OBSERVATION_STAGE, EventStage


@dataclass(frozen=True, slots=True)
class Observation:
    trace_id: str
    source: str
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=utc_now)
    stage: EventStage = OBSERVATION_STAGE
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "source": self.source,
            "timestamp": serialize_timestamp(self.timestamp),
            "payload": self.payload,
            "stage": self.stage.name,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }
