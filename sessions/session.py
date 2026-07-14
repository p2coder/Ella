from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from agent.handoff import HandoffRequest

from .execution_state import StepExecutionState


class TaskState(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    RUNNING = "running"
    REPLANNING = "replanning"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ALLOWED_TASK_STATE_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.CREATED: frozenset({TaskState.PLANNING}),
    TaskState.PLANNING: frozenset(
        {
            TaskState.RUNNING,
            TaskState.WAITING,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.RUNNING: frozenset(
        {
            TaskState.REPLANNING,
            TaskState.WAITING,
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.REPLANNING: frozenset(
        {
            TaskState.RUNNING,
            TaskState.WAITING,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.WAITING: frozenset(
        {
            TaskState.PLANNING,
            TaskState.CANCELLED,
        }
    ),
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


@dataclass(slots=True)
class TaskSession:
    session_id: str
    task_id: str
    handoff: HandoffRequest
    state: TaskState = TaskState.CREATED
    task_local_state: dict[str, Any] = field(default_factory=dict)
    message_history: tuple[dict[str, Any], ...] = ()
    tool_trace: tuple[dict[str, Any], ...] = ()
    current_strategy: Any | None = None
    completion: Any | None = None
    failure_reason: str | None = None
    current_step: StepExecutionState = field(default_factory=StepExecutionState)
    step_history: tuple[StepExecutionState, ...] = ()

    def set_task_state(self, key: str, value: Any) -> None:
        self.task_local_state[key] = value

    def transition_to(self, next_state: TaskState) -> None:
        if next_state not in ALLOWED_TASK_STATE_TRANSITIONS[self.state]:
            raise ValueError(
                "invalid task state transition: "
                f"{self.state.value} -> {next_state.value}"
            )
        self.state = next_state
