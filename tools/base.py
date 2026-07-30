from dataclasses import dataclass
from enum import StrEnum
import inspect
from typing import Any, Protocol, Sequence
import warnings

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
    version: str = "1"
    idempotency: ToolIdempotency = ToolIdempotency.UNKNOWN
    side_effecting: bool = False
    uncertain_policy: ToolUncertainPolicy = ToolUncertainPolicy.NEVER
    overridable_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty_string("name", self.name)
        _require_non_empty_string("description", self.description)
        _require_non_empty_string("schema_version", self.schema_version)
        _require_non_empty_string("version", self.version)
        _require_object_schema("input_schema", self.input_schema)
        _require_object_schema("output_schema", self.output_schema)
        if not isinstance(self.idempotency, ToolIdempotency):
            raise TypeError("idempotency must be a ToolIdempotency")
        if not isinstance(self.side_effecting, bool):
            raise TypeError("side_effecting must be a boolean")
        if not isinstance(self.uncertain_policy, ToolUncertainPolicy):
            raise TypeError("uncertain_policy must be a ToolUncertainPolicy")
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
        }


@dataclass(frozen=True, slots=True)
class EffectiveToolExecutionMetadata:
    name: str
    version: str
    idempotency: ToolIdempotency
    side_effecting: bool
    uncertain_policy: ToolUncertainPolicy
    overridden_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, init=False)
class ToolResult:
    tool_name: str
    task_id: str
    trace_id: str
    payload: dict[str, Any]

    def __init__(
        self,
        tool_name: str,
        task_id: str,
        trace_id: str,
        payload: dict[str, Any],
        session_id: str | None = None,
    ) -> None:
        object.__setattr__(self, "tool_name", tool_name)
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "trace_id", trace_id)
        object.__setattr__(self, "payload", payload)

    @property
    def session_id(self) -> str:
        return self.task_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "payload": self.payload,
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


def invoke_tool(
    tool: Tool,
    context: AgentExecutionContext,
    arguments: dict[str, object],
) -> ToolResult:
    parameters = inspect.signature(tool.run).parameters.values()
    supports_arguments = any(
        parameter.name == "arguments"
        or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )
    if supports_arguments:
        return tool.run(context=context, arguments=arguments)

    if arguments:
        warnings.warn(
            f"tool {tool.name} uses deprecated run(context) and cannot consume "
            "validated arguments",
            DeprecationWarning,
            stacklevel=2,
        )
    return tool.run(context)
