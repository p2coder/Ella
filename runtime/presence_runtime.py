from collections.abc import Callable
from dataclasses import dataclass

from events import StandardizedEvent
from runtime.event_queue import PresenceQueue
from runtime.interruption_policy import InterruptionPolicy


@dataclass(frozen=True, slots=True)
class PresenceRuntimeResult:
    consumed_count: int
    allowed_count: int
    suppressed_count: int


@dataclass(slots=True)
class PresenceRuntime:
    presence_queue: PresenceQueue
    next_boundary: Callable[[StandardizedEvent], None] | None = None
    interruption_policy: InterruptionPolicy = InterruptionPolicy()

    def process_available(self) -> PresenceRuntimeResult:
        consumed_count = 0
        allowed_count = 0
        suppressed_count = 0

        while True:
            event = self.presence_queue.dequeue()
            if event is None:
                break

            consumed_count += 1
            decision = self.interruption_policy.evaluate(event)
            if decision.allowed:
                allowed_count += 1
                if self.next_boundary is not None:
                    self.next_boundary(event)
            else:
                suppressed_count += 1

        return PresenceRuntimeResult(
            consumed_count=consumed_count,
            allowed_count=allowed_count,
            suppressed_count=suppressed_count,
        )
