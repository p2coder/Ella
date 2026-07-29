"""Deprecated import compatibility; no runtime state is owned here."""

from agent.strategy import StrategyDecision
from agent.subagent import SubAgent
from runtime.executor import CapabilityExecutionResult, CapabilityExecutor
from tasks.factory import TaskCreationResult, TaskFactory
from tasks.task import Task, TaskState

TaskSession = Task
TaskSessionCreation = TaskCreationResult
TaskSessionManager = TaskFactory

__all__ = [
    "CapabilityExecutionResult",
    "CapabilityExecutor",
    "StrategyDecision",
    "SubAgent",
    "Task",
    "TaskCreationResult",
    "TaskFactory",
    "TaskSession",
    "TaskSessionCreation",
    "TaskSessionManager",
    "TaskState",
]
