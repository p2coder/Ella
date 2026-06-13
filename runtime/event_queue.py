from collections import deque
from dataclasses import dataclass, field

from events import StandardizedEvent


@dataclass(slots=True)
class PresenceQueue:
    _events: deque[StandardizedEvent] = field(default_factory=deque)

    def enqueue(self, event: StandardizedEvent) -> None:
        self._events.append(event)

    def dequeue(self) -> StandardizedEvent | None:
        if not self._events:
            return None
        return self._events.popleft()

    def __len__(self) -> int:
        return len(self._events)
