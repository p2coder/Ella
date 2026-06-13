from dataclasses import dataclass
from typing import Any, Sequence

from .event import StandardizedEvent
from .signal import RawSignal
from .stage import STANDARDIZED_EVENT_STAGE, EventStage


class PipelineStage:
    stage: EventStage

    def process(self, item: Any) -> Any:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class EventTriggerPipeline:
    stages: Sequence[PipelineStage]

    def run(self, item: Any) -> Any:
        current = item
        for stage in self.stages:
            current = stage.process(current)
        return current


@dataclass(frozen=True, slots=True)
class CliTextToStandardizedEventStage(PipelineStage):
    stage: EventStage = STANDARDIZED_EVENT_STAGE
    event_type: str = "USER_UTTERANCE"
    confidence: float = 1.0
    priority: float = 0.9
    trigger_kind: str = "user_initiated"

    def process(self, item: RawSignal) -> StandardizedEvent:
        if not isinstance(item, RawSignal):
            raise TypeError("CliTextToStandardizedEventStage expects a RawSignal")

        text = item.payload.get("text")
        if not isinstance(text, str):
            raise ValueError("CLI text signal payload must contain text")

        return StandardizedEvent(
            trace_id=item.trace_id,
            source=item.source,
            timestamp=item.timestamp,
            payload={"text": text},
            event_type=self.event_type,
            confidence=self.confidence,
            priority=self.priority,
            metadata=item.metadata | {"trigger_kind": self.trigger_kind},
        )
