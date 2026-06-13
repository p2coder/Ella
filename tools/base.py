from dataclasses import dataclass
from typing import Any, Protocol

from agent.context import AgentExecutionContext


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
