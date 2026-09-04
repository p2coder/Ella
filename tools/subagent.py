from dataclasses import dataclass
from typing import Any

from agent.child_runner import ChildAgentRunner
from agent.context import AgentExecutionContext

from .base import CapabilityKind, ToolDefinition, ToolResult


def _definition(name: str, description: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        schema_version="1.0",
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "timeout_seconds": {"type": "number"},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
        input_examples=({"prompt": "Analyze the bounded question."},),
        output_schema={
            "type": "object",
            "properties": {
                "child_agent_id": {"type": "string"},
                "status": {"type": "string"},
                "final_response": {"type": ["string", "null"]},
                "observations": {"type": "array"},
                "error": {"type": ["string", "null"]},
                "provider_usage": {"type": ["object", "null"]},
                "completed_at": {"type": "string"},
                "mode": {"type": "string"},
                "depth": {"type": "number"},
                "parent_agent_id": {"type": "string"},
                "capability_scope": {"type": "object"},
                "started_at": {"type": "string"},
                "provider_usage_calls": {"type": "array"},
            },
            "required": [
                "child_agent_id",
                "status",
                "final_response",
                "observations",
                "error",
                "provider_usage",
                "completed_at",
                "mode",
                "depth",
                "parent_agent_id",
                "capability_scope",
                "started_at",
                "provider_usage_calls",
            ],
            "additionalProperties": False,
        },
        result_ttl_seconds=None,
        capability_kind=CapabilityKind.RUNTIME,
    )


@dataclass(frozen=True, slots=True)
class SubagentTool:
    runner: ChildAgentRunner
    name: str = "subagent"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    @property
    def definition(self) -> ToolDefinition:
        return _definition(
            self.name,
            "Run a bounded child agent with a clean context and inherited permissions.",
        )

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict[str, object] | None = None,
    ) -> ToolResult:
        values = arguments or {}
        run = self.runner.run(
            context,
            prompt=str(values.get("prompt", "")),
            timeout_seconds=float(values.get("timeout_seconds", 120)),
        )
        return ToolResult(
            self.name, context.task_id, context.trace_id, run.to_dict()
        )


@dataclass(frozen=True, slots=True)
class SubagentForkTool:
    runner: ChildAgentRunner
    name: str = "subagent_fork"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    @property
    def definition(self) -> ToolDefinition:
        return _definition(
            self.name,
            "Run a bounded child agent with a dispatch-time copy of the parent context.",
        )

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict[str, object] | None = None,
    ) -> ToolResult:
        values = arguments or {}
        run = self.runner.run(
            context,
            prompt=str(values.get("prompt", "")),
            timeout_seconds=float(values.get("timeout_seconds", 120)),
            fork=True,
        )
        return ToolResult(
            self.name, context.task_id, context.trace_id, run.to_dict()
        )
