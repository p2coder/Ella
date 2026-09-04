from dataclasses import dataclass

from agent.context import AgentExecutionContext
from runtime.workflow_runtime import WorkflowRuntime

from .base import (
    CapabilityKind,
    ToolDefinition,
    ToolResult,
    ToolUncertainPolicy,
)


@dataclass(frozen=True, slots=True)
class WorkflowTool:
    runtime: WorkflowRuntime
    name: str = "workflow"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Run one complete JavaScript program that orchestrates only "
                "subagent and subagent_fork with await or Promise.all."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {"script": {"type": "string"}},
                "required": ["script"],
                "additionalProperties": False,
            },
            input_examples=(
                {"script": "return await tools.subagent({prompt: 'Analyze A'});"},
            ),
            output_schema={
                "type": "object",
                "properties": {
                    "script_return_value": {},
                    "child_results": {"type": "array"},
                },
                "required": ["script_return_value", "child_results"],
                "additionalProperties": False,
            },
            result_ttl_seconds=None,
            side_effecting=True,
            uncertain_policy=ToolUncertainPolicy.POSSIBLE_AFTER_DISPATCH,
            capability_kind=CapabilityKind.RUNTIME,
        )

    def run(self, context: AgentExecutionContext, arguments=None) -> ToolResult:
        payload = self.runtime.execute(context, str((arguments or {}).get("script", "")))
        return ToolResult(self.name, context.task_id, context.trace_id, payload)
