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
                "when the goal requires multiple staged outcomes; do not use for "
                "simple direct tasks or progress updates. Each step must represent "
                "one independently executable and observable intermediate goal, "
                "not one Tool call. Split independent work items, such as research "
                "for separate projects, into separate steps so they can run in the "
                "same wave. Keep closely related actions for one item and stage in "
                "one step; do not split searching, opening, and reading the same "
                "source into separate steps. Describe the outcome in goal without "
                "binding it to a Tool name. completion_criteria must describe "
                "observable output facts rather than whether a Tool ran. Enumerate "
                "criteria whenever expected facts can be enumerated, and do not use "
                "vague words such as sufficient, comprehensive, complete, or "
                "high-quality as the only criterion. Criteria may be empty for a "
                "non-critical step, but a critical, irreplaceable step must have "
                "verifiable criteria. depends_on expresses real success dependency: "
                "a step runs only after every dependency succeeds. Independent "
                "steps must not depend on each other. If an existing plan is blocked "
                "by a failed step, write a revised plan that preserves reusable "
                "successful work, replaces the blocked path, and keeps failed or "
                "missing evidence visible to later reasoning. Reuse a successful "
                "step_id only when its goal, criteria, and dependencies are "
                "unchanged; otherwise use a new step_id. For factual work, preserve "
                "traceable sources in Tool observations rather than copying source "
                "content into the plan."
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
