from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class ToolFailureKind(StrEnum):
    INVALID_ARGUMENTS = "invalid_arguments"
    INVALID_ARGUMENTS_REPAIR_VIOLATION = "invalid_arguments_repair_violation"
    PERMISSION_DENIED = "permission_denied"
    ENVIRONMENT_UNAVAILABLE = "environment_unavailable"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"


class StepState(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    KILLED = "killed"
    SKIPPED = "skipped"


class ToolNodeState(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    SKIPPED = "skipped"


class ToolAttemptState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class StepToolAvailabilityState(StrEnum):
    AVAILABLE = "available"
    BLOCKED = "blocked"


class TaskControlType(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    KILL = "kill"
    RESOLVE_UNCERTAIN_AS_FAILED = "resolve_uncertain_as_failed"


class DeliveryOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DeliveryPayloadType(StrEnum):
    SUCCESS_RESULT = "success_result"
    FAILURE_REPORT = "failure_report"
    UNCERTAIN_FAILURE_REPORT = "uncertain_failure_report"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class ToolFailureObservation:
    attempt_id: str
    tool_name: str
    kind: ToolFailureKind
    code: str
    message: str
    arguments: Mapping[str, Any]
    retryable: bool
    tool_use_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    parent_agent_id: str | None = None
    called_at: str | None = None
    completed_at: str | None = None
    result_ttl_seconds: float | None = None

    def __post_init__(self) -> None:
        for field_name in ("attempt_id", "tool_name", "code", "message"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.kind, ToolFailureKind):
            raise TypeError("kind must be a ToolFailureKind")
        if not isinstance(self.arguments, Mapping):
            raise TypeError("arguments must be a mapping")
        object.__setattr__(self, "arguments", _freeze(self.arguments))

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "tool_name": self.tool_name,
            "kind": self.kind.value,
            "code": self.code,
            "message": self.message,
            "arguments": _thaw(self.arguments),
            "retryable": self.retryable,
            "tool_use_id": self.tool_use_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "parent_agent_id": self.parent_agent_id,
            "called_at": self.called_at,
            "completed_at": self.completed_at,
            "result_ttl_seconds": self.result_ttl_seconds,
        }


@dataclass(frozen=True, slots=True)
class TaskControlCommand:
    command_id: str
    task_id: str
    command_type: TaskControlType
    requested_at: datetime
    actor: str
    reason: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("command_id", "task_id", "actor"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.command_type, TaskControlType):
            raise TypeError("command_type must be a TaskControlType")


@dataclass(frozen=True, slots=True)
class TaskControlResult:
    command_id: str
    task_id: str
    accepted: bool
    previous_state: str
    current_state: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class StepToolAvailability:
    step_id: str
    tool_name: str
    state: StepToolAvailabilityState = StepToolAvailabilityState.AVAILABLE
    blocked_reason: str | None = None
    blocked_until: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in ("step_id", "tool_name"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.state is StepToolAvailabilityState.AVAILABLE and (
            self.blocked_reason is not None or self.blocked_until is not None
        ):
            raise ValueError("AVAILABLE tool cannot carry blocked details")


@dataclass(frozen=True, slots=True)
class ToolAttempt:
    attempt_id: str
    attempt_index: int
    arguments: Mapping[str, Any]
    state: ToolAttemptState
    result: Any | None = None
    failure: ToolFailureObservation | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.attempt_id.strip():
            raise ValueError("attempt_id must be non-empty")
        if self.attempt_index < 1:
            raise ValueError("attempt_index must start at 1")
        object.__setattr__(self, "arguments", _freeze(self.arguments))


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    attempt_id: str
    succeeded: bool
    attempted_at: datetime
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class TaskDeliveryRecord:
    outcome: DeliveryOutcome
    payload_type: DeliveryPayloadType
    payload: Any
    attempts: tuple[DeliveryAttempt, ...] = ()
    delivered_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class UncertainResolutionRecord:
    resolution: str
    tool_name: str
    arguments: Mapping[str, Any]
    invoked_at: datetime | None
    reason: str
    possible_side_effects: tuple[str, ...]
    resolved_at: datetime

    def __post_init__(self) -> None:
        if self.resolution != "treated_as_failed":
            raise ValueError("unsupported uncertain resolution")
        object.__setattr__(self, "arguments", _freeze(self.arguments))
        object.__setattr__(self, "possible_side_effects", tuple(self.possible_side_effects))


def any_terminal_succeeded(
    states: Mapping[str, StepState | ToolNodeState],
    terminal_node_ids: tuple[str, ...],
) -> bool:
    succeeded_values = {StepState.SUCCEEDED, ToolNodeState.SUCCEEDED}
    return any(states.get(node_id) in succeeded_values for node_id in terminal_node_ids)


@dataclass(frozen=True, slots=True)
class StepExecutionState:
    step_number: int = 1
    retry_index: int = 0
    max_step_retries: int = 2
    active_tool_name: str | None = None
    blacklisted_tools: tuple[str, ...] = ()
    failures: tuple[ToolFailureObservation, ...] = ()

    def __post_init__(self) -> None:
        if self.step_number < 1:
            raise ValueError("step_number must be at least 1")
        if self.retry_index < 0:
            raise ValueError("retry_index must be non-negative")
        if self.max_step_retries < 0:
            raise ValueError("max_step_retries must be non-negative")
        if self.retry_index > self.max_step_retries:
            raise ValueError("retry_index must not exceed max_step_retries")
        if self.active_tool_name is not None and not self.active_tool_name.strip():
            raise ValueError("active_tool_name must be non-empty when provided")
        object.__setattr__(
            self,
            "blacklisted_tools",
            tuple(dict.fromkeys(self.blacklisted_tools)),
        )
        object.__setattr__(self, "failures", tuple(self.failures))

    @property
    def attempt_id(self) -> str:
        if self.retry_index == 0:
            return f"step{self.step_number}_try"
        return f"step{self.step_number}_retry{self.retry_index}"

    @property
    def retries_remaining(self) -> int:
        return self.max_step_retries - self.retry_index

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_number": self.step_number,
            "retry_index": self.retry_index,
            "max_step_retries": self.max_step_retries,
            "attempt_id": self.attempt_id,
            "active_tool_name": self.active_tool_name,
            "blacklisted_tools": self.blacklisted_tools,
            "failures": tuple(failure.to_dict() for failure in self.failures),
        }
