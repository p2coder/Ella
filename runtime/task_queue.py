from collections import deque
from dataclasses import dataclass, field


@dataclass(slots=True)
class TaskQueue:
    _items: deque[str] = field(default_factory=deque)
    _known: set[str] = field(default_factory=set)

    def enqueue(self, task_id: str) -> bool:
        if not task_id:
            raise ValueError("task_id must not be empty")
        if task_id in self._known:
            return False
        self._items.append(task_id)
        self._known.add(task_id)
        return True

    def dequeue(self) -> str | None:
        if not self._items:
            return None
        task_id = self._items.popleft()
        self._known.remove(task_id)
        return task_id

    def discard(self, task_id: str) -> None:
        if task_id not in self._known:
            return
        self._items = deque(item for item in self._items if item != task_id)
        self._known.remove(task_id)

    def snapshot(self) -> tuple[str, ...]:
        return tuple(self._items)

