from dataclasses import dataclass

from agent.context import AgentExecutionContext
from runtime.plan_store import PlanStep, PlanStore
from .base import CapabilityKind, ToolDefinition, ToolResult


def _step_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "step_id": {"type": "string"},
            "goal": {"type": "string"},
            "completion_criteria": {
                "type": "array",
                "items": {"type": "string"},
            },
            "depends_on": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["step_id", "goal", "completion_criteria"],
        "additionalProperties": False,
    }


@dataclass(frozen=True, slots=True)
class PlanWrittenTool:
    store: PlanStore
    name: str = "plan_written"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Create or structurally replace the current Task plan. Use only "
                "when the goal requires multiple dependent steps. Do not use for "
                "simple direct tasks or progress updates."
            ),
            schema_version="2.0",
            input_schema={
                "type": "object",
                "properties": {
                    "steps": {"type": "array", "items": _step_schema()},
                },
                "required": ["steps"],
                "additionalProperties": False,
            },
            input_examples=(),
            output_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "version_id": {"type": "string"},
                    "parent_version_id": {"type": "string"},
                    "content_digest": {"type": "string"},
                    "steps": {"type": "array", "items": _step_schema()},
                },
                "required": ["task_id", "version_id", "content_digest", "steps"],
                "additionalProperties": False,
            },
            capability_kind=CapabilityKind.RUNTIME,
        )

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict | None = None,
    ) -> ToolResult:
        args = arguments or {}
        steps = tuple(
            PlanStep(
                item["step_id"],
                item["goal"],
                tuple(item["completion_criteria"]),
                tuple(item.get("depends_on", ())),
            )
            for item in args["steps"]
        )
        record = self.store.write(task_id=context.task_id, steps=steps)
        payload = record.to_dict()
        if payload["parent_version_id"] is None:
            payload.pop("parent_version_id")
        payload.pop("created_from_decision_id", None)
        return ToolResult(self.name, context.task_id, context.trace_id, payload)
