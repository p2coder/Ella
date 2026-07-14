from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class ToolFailureKind(StrEnum):
    INVALID_ARGUMENTS = "invalid_arguments"
    INVALID_ARGUMENTS_REPAIR_VIOLATION = "invalid_arguments_repair_violation"
    PERMISSION_DENIED = "permission_denied"
    ENVIRONMENT_UNAVAILABLE = "environment_unavailable"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"


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
        }


@dataclass(frozen=True, slots=True)
class StepExecutionState:
    step_number: int = 1
    retry_index: int = 0
    max_argument_retries: int = 2
    active_tool_name: str | None = None
    blacklisted_tools: tuple[str, ...] = ()
    failures: tuple[ToolFailureObservation, ...] = ()

    def __post_init__(self) -> None:
        if self.step_number < 1:
            raise ValueError("step_number must be at least 1")
        if self.retry_index < 0:
            raise ValueError("retry_index must be non-negative")
        if self.max_argument_retries < 0:
            raise ValueError("max_argument_retries must be non-negative")
        if self.retry_index > self.max_argument_retries:
            raise ValueError("retry_index must not exceed max_argument_retries")
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
        return self.max_argument_retries - self.retry_index

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_number": self.step_number,
            "retry_index": self.retry_index,
            "max_argument_retries": self.max_argument_retries,
            "attempt_id": self.attempt_id,
            "active_tool_name": self.active_tool_name,
            "blacklisted_tools": self.blacklisted_tools,
            "failures": tuple(failure.to_dict() for failure in self.failures),
        }
