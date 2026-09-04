from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from agent.context import AgentExecutionContext
from events import StandardizedEvent

from .state import StepExecutionState


class TaskState(StrEnum):
    CREATED = "created"
    READY = "ready"
    REASONING = "reasoning"
    TOOL_EXECUTION = "tool_execution"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    KILL_REQUESTED = "kill_requested"
    COMPLETED = "completed"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    KILLED = "killed"
    DELIVERED = "delivered"


class TaskGoalState(StrEnum):
    ACHIEVED = "achieved"
    PARTIALLY_ACHIEVED = "partially_achieved"
    NOT_ACHIEVED = "not_achieved"


@dataclass(frozen=True, slots=True)
class TaskIntent:
    goal: str
    constraints: tuple[str, ...] = ()
    deliverables: tuple[str, ...] = ()
    minimum_acceptance_criteria: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.goal.strip():
            raise ValueError("TaskIntent goal must be non-empty")
        for field_name in (
            "constraints",
            "deliverables",
            "minimum_acceptance_criteria",
        ):
            values = tuple(getattr(self, field_name))
            if any(not isinstance(item, str) or not item.strip() for item in values):
                raise ValueError(f"TaskIntent {field_name} must contain non-empty strings")
            object.__setattr__(self, field_name, values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "constraints": self.constraints,
            "deliverables": self.deliverables,
            "minimum_acceptance_criteria": self.minimum_acceptance_criteria,
        }


ALLOWED_TASK_STATE_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.CREATED: frozenset(
        {
            TaskState.READY,
            TaskState.PAUSE_REQUESTED,
            TaskState.KILL_REQUESTED,
        }
    ),
    TaskState.READY: frozenset(
        {
            TaskState.REASONING,
            TaskState.PAUSE_REQUESTED,
            TaskState.KILL_REQUESTED,
        }
    ),
    TaskState.REASONING: frozenset(
        {
            TaskState.TOOL_EXECUTION,
            TaskState.PAUSE_REQUESTED,
            TaskState.KILL_REQUESTED,
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.UNCERTAIN,
        }
    ),
    TaskState.TOOL_EXECUTION: frozenset(
        {
            TaskState.REASONING,
            TaskState.PAUSE_REQUESTED,
            TaskState.KILL_REQUESTED,
            TaskState.FAILED,
            TaskState.UNCERTAIN,
        }
    ),
    TaskState.PAUSE_REQUESTED: frozenset(
        {
            TaskState.PAUSED,
            TaskState.KILL_REQUESTED,
        }
    ),
    TaskState.PAUSED: frozenset(
        {
            TaskState.READY,
            TaskState.REASONING,
            TaskState.TOOL_EXECUTION,
            TaskState.KILL_REQUESTED,
        }
    ),
    TaskState.KILL_REQUESTED: frozenset({TaskState.KILLED}),
    TaskState.COMPLETED: frozenset({TaskState.DELIVERED}),
    TaskState.FAILED: frozenset({TaskState.DELIVERED}),
    TaskState.UNCERTAIN: frozenset({TaskState.FAILED, TaskState.DELIVERED}),
    TaskState.KILLED: frozenset({TaskState.DELIVERED}),
    TaskState.DELIVERED: frozenset(),
}


@dataclass(slots=True)
class Task:
    task_id: str
    state: TaskState = TaskState.CREATED
    goal_state: TaskGoalState | None = None
    terminal_execution_state: TaskState | None = None
    intent: TaskIntent | None = None
    first_decision_completed: bool = False
    task_local_state: dict[str, Any] = field(default_factory=dict)
    message_history: tuple[dict[str, Any], ...] = ()
    tool_trace: tuple[dict[str, Any], ...] = ()
    completion: Any | None = None
    failure_reason: str | None = None
    current_step: StepExecutionState = field(default_factory=StepExecutionState)
    step_history: tuple[StepExecutionState, ...] = ()
    trace_id: str = ""
    source_event: StandardizedEvent | None = None
    execution_context: AgentExecutionContext | None = None
    paused_from_state: TaskState | None = None
    terminal_outcome: Any | None = None
    failure: Any | None = None
    uncertain_resolution: Any | None = None
    delivery: Any | None = None
    control_request: Any | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def set_task_state(self, key: str, value: Any) -> None:
        self.task_local_state[key] = value

    def transition_to(self, next_state: TaskState) -> None:
        if next_state not in ALLOWED_TASK_STATE_TRANSITIONS[self.state]:
            raise ValueError(
                "invalid task state transition: "
                f"{self.state.value} -> {next_state.value}"
            )
        previous_state = self.state
        if next_state in {TaskState.KILLED, TaskState.UNCERTAIN}:
            self.goal_state = TaskGoalState.NOT_ACHIEVED
        elif next_state is TaskState.FAILED and self.goal_state is None:
            self.goal_state = TaskGoalState.NOT_ACHIEVED
        elif next_state is TaskState.DELIVERED:
            if self.terminal_execution_state is None:
                self.terminal_execution_state = previous_state
            if self.goal_state is None:
                raise ValueError("DELIVERED Task requires a committed goal state")
        self.state = next_state
        self.updated_at = datetime.now(timezone.utc)

    def set_goal_state(self, goal_state: TaskGoalState) -> None:
        if self.state not in {
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.UNCERTAIN,
            TaskState.KILLED,
            TaskState.DELIVERED,
        }:
            raise ValueError("goal state may only be committed at a terminal boundary")
        self.goal_state = goal_state
        self.updated_at = datetime.now(timezone.utc)
