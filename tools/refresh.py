from agent.context import AgentExecutionContext

from .base import CapabilityKind, ToolDefinition, ToolResult


class RefreshTool:
    """Runtime marker tool; CapabilityExecutor performs the replay."""

    name = "refresh"
    allowed_roles = ("main_agent", "subagent")

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Replay a prior tool use with the same tool and validated arguments."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {"tool_use_id": {"type": "string"}},
                "required": ["tool_use_id"],
                "additionalProperties": False,
            },
            input_examples=({"tool_use_id": "tool-use-123"},),
            output_schema={"type": "object"},
            result_ttl_seconds=0,
            capability_kind=CapabilityKind.RUNTIME,
        )

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict[str, object] | None = None,
    ) -> ToolResult:
        raise RuntimeError("refresh must be dispatched by CapabilityExecutor")
