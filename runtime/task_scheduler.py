from dataclasses import dataclass, field

from sessions.session import Task, TaskState

from .task_queue import TaskQueue
from .task_store import StoredTask, TaskStore, TaskVersionConflict


@dataclass(slots=True)
class TaskScheduler:
    store: TaskStore
    queue: TaskQueue = field(default_factory=TaskQueue)
    recovery_queue: TaskQueue = field(default_factory=TaskQueue)

    def enqueue_ready(self, task_id: str) -> bool:
        record = self.store.load(task_id)
        if record is None or record.task.state is not TaskState.READY:
            return False
        return self.queue.enqueue(task_id)

    def claim_next(self) -> Task | None:
        while (task_id := self.queue.dequeue()) is not None:
            record = self.store.load(task_id)
            if record is None or record.task.state is not TaskState.READY:
                continue
            record.task.transition_to(TaskState.RUNNING)
            try:
                self.store.save(record.task, expected_version=record.version)
            except TaskVersionConflict:
                continue
            return record.task
        return None

    def rebuild(self) -> None:
        self.queue = TaskQueue()
        self.recovery_queue = TaskQueue()
        for record in self.store.list():
            state = record.task.state
            if state is TaskState.READY:
                self.queue.enqueue(record.task.task_id)
            elif state in {
                TaskState.RUNNING,
                TaskState.PAUSE_REQUESTED,
                TaskState.KILL_REQUESTED,
            }:
                self.recovery_queue.enqueue(record.task.task_id)

    def next_recovery(self) -> StoredTask | None:
        task_id = self.recovery_queue.dequeue()
        return None if task_id is None else self.store.load(task_id)

