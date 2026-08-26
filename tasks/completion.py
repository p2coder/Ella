from dataclasses import dataclass
from typing import Any

from agent.context import AgentExecutionContext
from tasks.output import UserVisibleAgentOutput
from tools import ToolResult


@dataclass(frozen=True, slots=True)
class FailureDeliveryPayload:
    task_goal: str
    reason: str
    trustworthy_observations: tuple[str, ...] = ()
    failed_nodes: tuple[str, ...] = ()
    user_fixable_causes: tuple[str, ...] = ()
    unknown_side_effects: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_goal": self.task_goal,
            "outcome": "failed",
            "reason": self.reason,
            "trustworthy_observations": self.trustworthy_observations,
            "failed_nodes": self.failed_nodes,
            "user_fixable_causes": self.user_fixable_causes,
            "unknown_side_effects": self.unknown_side_effects,
        }


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
