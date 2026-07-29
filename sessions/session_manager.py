"""Deprecated compatibility aliases; task creation is owned by tasks.factory."""

from tasks.factory import TaskCreationResult, TaskFactory

TaskSessionCreation = TaskCreationResult
TaskSessionManager = TaskFactory

__all__ = [
    "TaskCreationResult",
    "TaskFactory",
    "TaskSessionCreation",
    "TaskSessionManager",
]
