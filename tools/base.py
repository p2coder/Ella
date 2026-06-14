from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from agent.context import AgentExecutionContext


def _require_non_empty_string(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_object_schema(field_name: str, value: dict[str, Any]) -> None:
    if not isinstance(value, dict) or value.get("type") != "object":
        raise ValueError(f"{field_name} must be an object schema")


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    schema_version: str
    input_schema: dict[str, Any]
    input_examples: Sequence[dict[str, Any]]
    output_schema: dict[str, Any]

    def __post_init__(self) -> None:
        _require_non_empty_string("name", self.name)
        _require_non_empty_string("description", self.description)
        _require_non_empty_string("schema_version", self.schema_version)
        _require_object_schema("input_schema", self.input_schema)
        _require_object_schema("output_schema", self.output_schema)
        object.__setattr__(self, "input_examples", tuple(self.input_examples))

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
class ToolResult:
    tool_name: str
    task_id: str
    session_id: str
    trace_id: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "payload": self.payload,
        }


class Tool(Protocol):
    name: str
    allowed_roles: tuple[str, ...]

    def run(self, context: AgentExecutionContext) -> ToolResult:
        ...
