from dataclasses import dataclass
from typing import Any

from agent.context import AgentExecutionContext
from sessions.output import UserVisibleAgentOutput
from tools import ToolResult


@dataclass(frozen=True, slots=True)
class TaskCompletionPackage:
    context: AgentExecutionContext
    summary: str
    user_visible_output: UserVisibleAgentOutput
    tool_results: tuple[ToolResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context.to_dict(),
            "summary": self.summary,
            "user_visible_output": self.user_visible_output.to_dict(),
            "tool_results": tuple(result.to_dict() for result in self.tool_results),
        }
