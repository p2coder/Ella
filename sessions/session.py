"""Deprecated compatibility aliases; Task state is owned by :mod:`tasks.task`."""

from tasks.task import Task, TaskState

TaskSession = Task

__all__ = ["Task", "TaskSession", "TaskState"]
