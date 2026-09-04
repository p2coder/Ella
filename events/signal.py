from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def serialize_timestamp(timestamp: datetime) -> str:
    return timestamp.isoformat()


@dataclass(frozen=True, slots=True)
class RawSignal:
    task_id: str
    source: str
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=utc_now)
    signal_type: str = "raw_signal"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "source": self.source,
            "timestamp": serialize_timestamp(self.timestamp),
            "payload": self.payload,
            "signal_type": self.signal_type,
            "metadata": self.metadata,
        }
