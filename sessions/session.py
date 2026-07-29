from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from events import StandardizedEvent

from .execution_state import StepExecutionState
from .graph import TaskGraphNodeType, TaskGraphRun


class TaskState(StrEnum):
    CREATED = "created"
    FORMULATING = "formulating"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    KILL_REQUESTED = "kill_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    KILLED = "killed"
    DELIVERED = "delivered"

    # Deprecated compatibility states used by the pre-Task aggregate runtime.
    # They remain distinct until that runtime is migrated so its branch checks
    # keep their original meaning.
    PLANNING = "planning"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


ALLOWED_TASK_STATE_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.CREATED: frozenset(
        {
            TaskState.FORMULATING,
            TaskState.PLANNING,
            TaskState.PAUSE_REQUESTED,
            TaskState.KILL_REQUESTED,
        }
    ),
    TaskState.FORMULATING: frozenset(
        {
            TaskState.READY,
            TaskState.RUNNING,
            TaskState.WAITING,
            TaskState.PAUSE_REQUESTED,
            TaskState.KILL_REQUESTED,
            TaskState.FAILED,
        }
    ),
    TaskState.READY: frozenset(
        {
            TaskState.RUNNING,
            TaskState.PAUSE_REQUESTED,
            TaskState.KILL_REQUESTED,
        }
    ),
    TaskState.RUNNING: frozenset(
        {
            TaskState.RUNNING,
            TaskState.REPLANNING,
            TaskState.WAITING,
            TaskState.PAUSE_REQUESTED,
            TaskState.KILL_REQUESTED,
            TaskState.SUCCEEDED,
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.UNCERTAIN,
            TaskState.CANCELLED,
        }
    ),
    TaskState.WAITING: frozenset(
        {
            TaskState.FORMULATING,
            TaskState.READY,
            TaskState.RUNNING,
            TaskState.PAUSE_REQUESTED,
            TaskState.KILL_REQUESTED,
            TaskState.PLANNING,
            TaskState.CANCELLED,
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
            TaskState.CREATED,
            TaskState.FORMULATING,
            TaskState.READY,
            TaskState.RUNNING,
            TaskState.WAITING,
            TaskState.KILL_REQUESTED,
        }
    ),
    TaskState.KILL_REQUESTED: frozenset({TaskState.KILLED}),
    TaskState.SUCCEEDED: frozenset({TaskState.DELIVERED}),
    TaskState.FAILED: frozenset({TaskState.DELIVERED}),
    TaskState.UNCERTAIN: frozenset({TaskState.FAILED}),
    TaskState.KILLED: frozenset(),
    TaskState.DELIVERED: frozenset(),
    # Legacy TaskSession lifecycle. New Task code must use the canonical states
    # above; these entries only keep the current runtime runnable during staged
    # migration.
    TaskState.PLANNING: frozenset(
        {
            TaskState.RUNNING,
            TaskState.REPLANNING,
            TaskState.WAITING,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.REPLANNING: frozenset(
        {
            TaskState.RUNNING,
            TaskState.WAITING,
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.COMPLETED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


@dataclass(slots=True)
class Task:
    # Deprecated constructor identity retained until PR 5 removes session_id
    # from all public protocols.
    session_id: str
    task_id: str
    handoff: HandoffRequest | None = None
    state: TaskState = TaskState.CREATED
    task_local_state: dict[str, Any] = field(default_factory=dict)
    message_history: tuple[dict[str, Any], ...] = ()
    tool_trace: tuple[dict[str, Any], ...] = ()
    current_strategy: Any | None = None
    completion: Any | None = None
    failure_reason: str | None = None
    current_step: StepExecutionState = field(default_factory=StepExecutionState)
    step_history: tuple[StepExecutionState, ...] = ()
    trace_id: str = ""
    source_event: StandardizedEvent | None = None
    execution_context: AgentExecutionContext | None = None
    graph: TaskGraphRun | None = None
    waiting_condition: Any | None = None
    paused_from_state: TaskState | None = None
    terminal_outcome: Any | None = None
    failure: Any | None = None
    uncertain_resolution: Any | None = None
    delivery: Any | None = None
    control_request: Any | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def active_step_ids(self) -> tuple[str, ...]:
        if self.graph is None:
            return ()
        step_ids = {
            node.node_id
            for node in self.graph.definition.nodes
            if node.node_type is TaskGraphNodeType.STEP
        }
        active_states = {"ready", "running", "paused"}
        return tuple(
            node_id
            for node_id in self.graph.definition.topological_order()
            if node_id in step_ids
            and _node_run_state(self.graph.node_runs.get(node_id)) in active_states
        )

    def set_task_state(self, key: str, value: Any) -> None:
        self.task_local_state[key] = value

    def transition_to(self, next_state: TaskState) -> None:
        if next_state not in ALLOWED_TASK_STATE_TRANSITIONS[self.state]:
            raise ValueError(
                "invalid task state transition: "
                f"{self.state.value} -> {next_state.value}"
            )
        self.state = next_state
        self.updated_at = datetime.now(timezone.utc)


def _node_run_state(node_run: Any) -> str | None:
    if node_run is None:
        return None
    value = (
        node_run.get("state")
        if isinstance(node_run, Mapping)
        else getattr(node_run, "state", None)
    )
    if value is None:
        return None
    return str(getattr(value, "value", value)).lower()


# Compatibility import only. This is the same aggregate, not another class.
TaskSession = Task
