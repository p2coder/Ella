"""Deprecated compatibility aliases; Task state is owned by :mod:`tasks.task`."""

from tasks.task import ALLOWED_TASK_STATE_TRANSITIONS, Task, TaskState

TaskSession = Task

__all__ = [
    "ALLOWED_TASK_STATE_TRANSITIONS",
    "Task",
    "TaskSession",
    "TaskState",
]
