from dataclasses import dataclass

from agent.context import AgentExecutionContext
from runtime.plan_store import PlanRecord, PlanStep, PlanStepStatus, PlanStore
from .base import ToolDefinition, ToolResult


@dataclass(frozen=True, slots=True)
class PlanWrittenTool:
    store: PlanStore
    name: str = "plan_written"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    @property
    def definition(self):
        step_schema = {"type": "object", "properties": {"step_id": {"type": "string"}, "goal": {"type": "string"}, "completion_criteria": {"type": "array", "items": {"type": "string"}}, "depends_on": {"type": "array", "items": {"type": "string"}}}, "required": ["step_id", "goal", "completion_criteria"], "additionalProperties": False}
        return ToolDefinition(self.name, "Create one immutable, versioned task plan. Use for decomposable tasks; do not use to update progress or accept file paths.", "1.0", {"type": "object", "properties": {"task_id": {"type": "string"}, "version_id": {"type": "string"}, "steps": {"type": "array", "items": step_schema}}, "required": ["task_id", "version_id", "steps"], "additionalProperties": False}, (), {"type": "object", "properties": {"task_id": {"type": "string"}, "version_id": {"type": "string"}, "revision": {"type": "number"}}, "required": ["task_id", "version_id", "revision"]})

    def run(self, context: AgentExecutionContext, arguments=None):
        args = arguments or {}
        if args.get("task_id") != context.task_id:
            raise ValueError("plan task_id must match execution context")
        steps = tuple(PlanStep(item["step_id"], item["goal"], tuple(item["completion_criteria"]), tuple(item.get("depends_on", ()))) for item in args["steps"])
        record = self.store.write(PlanRecord(context.task_id, args["version_id"], steps))
        return ToolResult(self.name, context.task_id, context.trace_id, {"task_id": record.task_id, "version_id": record.version_id, "revision": record.revision})


@dataclass(frozen=True, slots=True)
class PlanUpdateTool:
    store: PlanStore
    name: str = "plan_update"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    @property
    def definition(self):
        fields = {"task_id": {"type": "string"}, "version_id": {"type": "string"}, "step_id": {"type": "string"}, "expected_old_status": {"type": "string", "enum": [item.value for item in PlanStepStatus]}, "new_status": {"type": "string", "enum": [item.value for item in PlanStepStatus]}, "result_summary": {"type": "string"}}
        return ToolDefinition(self.name, "Update progress for one existing plan step with compare-and-set. Do not add, delete, reorder, or change dependencies.", "1.0", {"type": "object", "properties": fields, "required": ["task_id", "version_id", "step_id", "expected_old_status", "new_status"], "additionalProperties": False}, (), {"type": "object", "properties": {"revision": {"type": "number"}, "status": {"type": "string"}}, "required": ["revision", "status"]})

    def run(self, context: AgentExecutionContext, arguments=None):
        args = arguments or {}
        if args.get("task_id") != context.task_id:
            raise ValueError("plan task_id must match execution context")
        record = self.store.update_progress(context.task_id, args["version_id"], args["step_id"], PlanStepStatus(args["expected_old_status"]), PlanStepStatus(args["new_status"]), args.get("result_summary"))
        step = next(item for item in record.steps if item.step_id == args["step_id"])
        return ToolResult(self.name, context.task_id, context.trace_id, {"revision": record.revision, "status": step.status.value})
