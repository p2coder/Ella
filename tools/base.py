from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Any, Protocol, Sequence

from agent.context import AgentExecutionContext


def _require_non_empty_string(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_object_schema(field_name: str, value: dict[str, Any]) -> None:
    if not isinstance(value, dict) or value.get("type") != "object":
        raise ValueError(f"{field_name} must be an object schema")


class ToolIdempotency(StrEnum):
    IDEMPOTENT = "idempotent"
    NON_IDEMPOTENT = "non_idempotent"
    UNKNOWN = "unknown"


class ToolUncertainPolicy(StrEnum):
    NEVER = "never"
    POSSIBLE_AFTER_DISPATCH = "possible_after_dispatch"


class CapabilityKind(StrEnum):
    EXTERNAL = "external"
    RUNTIME = "runtime"
    INTERACTION = "interaction"


_OVERRIDABLE_EXECUTION_FIELDS = frozenset(
    {"idempotency", "side_effecting", "uncertain_policy"}
)


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    schema_version: str
    input_schema: dict[str, Any]
    input_examples: Sequence[dict[str, Any]]
    output_schema: dict[str, Any]
    result_ttl_seconds: float | None = None
    version: str = "1"
    idempotency: ToolIdempotency = ToolIdempotency.UNKNOWN
    side_effecting: bool = False
    uncertain_policy: ToolUncertainPolicy = ToolUncertainPolicy.NEVER
    overridable_fields: tuple[str, ...] = ()
    capability_kind: CapabilityKind = CapabilityKind.EXTERNAL

    def __post_init__(self) -> None:
        _require_non_empty_string("name", self.name)
        _require_non_empty_string("description", self.description)
        _require_non_empty_string("schema_version", self.schema_version)
        _require_non_empty_string("version", self.version)
        _require_object_schema("input_schema", self.input_schema)
        _require_object_schema("output_schema", self.output_schema)
        if self.result_ttl_seconds is not None:
            if (
                not isinstance(self.result_ttl_seconds, (int, float))
                or isinstance(self.result_ttl_seconds, bool)
                or not math.isfinite(self.result_ttl_seconds)
                or self.result_ttl_seconds < 0
            ):
                raise ValueError(
                    "result_ttl_seconds must be null or a finite non-negative number"
                )
        if not isinstance(self.idempotency, ToolIdempotency):
            raise TypeError("idempotency must be a ToolIdempotency")
        if not isinstance(self.side_effecting, bool):
            raise TypeError("side_effecting must be a boolean")
        if not isinstance(self.uncertain_policy, ToolUncertainPolicy):
            raise TypeError("uncertain_policy must be a ToolUncertainPolicy")
        if not isinstance(self.capability_kind, CapabilityKind):
            raise TypeError("capability_kind must be a CapabilityKind")
        overridable_fields = tuple(dict.fromkeys(self.overridable_fields))
        unknown_fields = set(overridable_fields) - _OVERRIDABLE_EXECUTION_FIELDS
        if unknown_fields:
            raise ValueError(
                "unsupported overridable fields: "
                + ", ".join(sorted(unknown_fields))
            )
        object.__setattr__(self, "input_examples", tuple(self.input_examples))
        object.__setattr__(self, "overridable_fields", overridable_fields)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "schema_version": self.schema_version,
            "input_schema": self.input_schema,
            "input_examples": self.input_examples,
            "output_schema": self.output_schema,
            "result_ttl_seconds": self.result_ttl_seconds,
            "capability_kind": self.capability_kind.value,
        }


@dataclass(frozen=True, slots=True)
class EffectiveToolExecutionMetadata:
    name: str
    version: str
    idempotency: ToolIdempotency
    side_effecting: bool
    uncertain_policy: ToolUncertainPolicy
    overridden_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_name: str
    task_id: str
    payload: dict[str, Any]
    tool_use_id: str | None = None
    agent_id: str | None = None
    parent_agent_id: str | None = None
    arguments: dict[str, Any] | None = None
    called_at: str | None = None
    completed_at: str | None = None
    result_ttl_seconds: float | None = None
    refresh_of_tool_use_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "task_id": self.task_id,
            "payload": self.payload,
            "tool_use_id": self.tool_use_id,
            "agent_id": self.agent_id,
            "parent_agent_id": self.parent_agent_id,
            "arguments": dict(self.arguments or {}),
            "called_at": self.called_at,
            "completed_at": self.completed_at,
            "result_ttl_seconds": self.result_ttl_seconds,
            "refresh_of_tool_use_id": self.refresh_of_tool_use_id,
        }


class Tool(Protocol):
    name: str
    allowed_roles: tuple[str, ...]

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict[str, object] | None = None,
    ) -> ToolResult:
        ...
