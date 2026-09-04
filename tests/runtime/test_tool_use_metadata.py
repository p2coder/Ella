from datetime import datetime, timezone

from agent.context import AgentExecutionContext, CapabilityScope
from agent.decision import CALL_TOOL, ExecutionDecision
from runtime.executor import CapabilityExecutor
from skill import SkillManager
from tasks.task import Task
from tools.base import ToolDefinition, ToolResult
from tools.manager import ToolManager


class EchoTool:
    name = "echo"
    allowed_roles = ("main_agent",)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description="Echo one value for tests.",
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            input_examples=({"value": "hello"},),
            output_schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            result_ttl_seconds=60,
        )

    def run(self, context, arguments=None) -> ToolResult:
        return ToolResult(
            self.name,
            context.task_id,
            {"value": str((arguments or {})["value"])},
        )


def _context() -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-metadata",
        memory_scope="task_local",
        capability_scope=CapabilityScope(
            agent_role="main_agent",
            allowed_skills=(),
            allowed_tools=("echo",),
        ),
    )


def test_executor_stamps_dispatched_tool_use() -> None:
    manager = ToolManager()
    manager.register(EchoTool())
    timestamps = iter(
        (
            datetime(2026, 9, 4, 1, 2, 3, tzinfo=timezone.utc),
            datetime(2026, 9, 4, 1, 2, 4, tzinfo=timezone.utc),
        )
    )
    executor = CapabilityExecutor(
        SkillManager(),
        manager,
        clock=lambda: next(timestamps),
        tool_use_id_factory=lambda: "tool-use-1",
    )
    decision = ExecutionDecision(
        CALL_TOOL,
        "echo",
        {"value": "hello"},
        "Echo the requested value.",
    )

    result = executor.execute(decision, _context(), Task("task-metadata"))

    assert result.failure is None
    assert result.tool_result is not None
    assert result.tool_result.tool_use_id == "tool-use-1"
    assert result.tool_result.agent_id == "ella-main"
    assert result.tool_result.arguments == {"value": "hello"}
    assert result.tool_result.called_at == "2026-09-04T01:02:03Z"
    assert result.tool_result.completed_at == "2026-09-04T01:02:04Z"
    assert result.tool_result.result_ttl_seconds == 60


def test_validation_failure_does_not_create_tool_use() -> None:
    manager = ToolManager()
    manager.register(EchoTool())
    executor = CapabilityExecutor(
        SkillManager(),
        manager,
        clock=lambda: (_ for _ in ()).throw(AssertionError("clock must not run")),
        tool_use_id_factory=lambda: (_ for _ in ()).throw(
            AssertionError("ID factory must not run")
        ),
    )
    decision = ExecutionDecision(
        CALL_TOOL,
        "echo",
        {},
        "Exercise validation.",
    )

    result = executor.execute(decision, _context(), Task("task-metadata"))

    assert result.failure is not None
    assert result.failure.tool_use_id is None
    assert result.failure.called_at is None
    assert result.failure.completed_at is None
