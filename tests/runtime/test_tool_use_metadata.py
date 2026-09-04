from datetime import datetime, timezone

from agent.context import AgentExecutionContext, CapabilityScope
from agent.decision import CALL_TOOL, ExecutionDecision
from runtime.executor import CapabilityExecutor
from skill import SkillManager
from tasks.task import Task
from tools.base import ToolDefinition, ToolResult, ToolUncertainPolicy
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


class ConfirmedFailure(RuntimeError):
    tool_outcome_uncertain = False


class ConfirmedFailureTool(EchoTool):
    name = "confirmed_failure"

    @property
    def definition(self) -> ToolDefinition:
        base = super().definition
        return ToolDefinition(
            name=self.name,
            description=base.description,
            schema_version=base.schema_version,
            input_schema=base.input_schema,
            input_examples=base.input_examples,
            output_schema=base.output_schema,
            side_effecting=True,
            uncertain_policy=ToolUncertainPolicy.POSSIBLE_AFTER_DISPATCH,
        )

    def run(self, context, arguments=None) -> ToolResult:
        raise ConfirmedFailure("execution failed with a confirmed outcome")


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
    manager = ToolManager({"echo": 15})
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

    dispatched = []
    result = executor.execute(
        decision,
        _context(),
        Task("task-metadata"),
        on_dispatch=lambda record, called_at, ttl: dispatched.append(
            (record, called_at, ttl)
        ),
    )

    assert result.failure is None
    assert result.tool_result is not None
    assert result.tool_result.tool_use_id == "tool-use-1"
    assert result.tool_result.agent_id == "ella-main"
    assert result.tool_result.arguments == {"value": "hello"}
    assert result.tool_result.called_at == "2026-09-04T01:02:03Z"
    assert result.tool_result.completed_at == "2026-09-04T01:02:04Z"
    assert result.tool_result.result_ttl_seconds == 15
    assert dispatched[0][0].tool_use_id == "tool-use-1"
    assert dispatched[0][0].arguments == {"value": "hello"}
    assert dispatched[0][1] == "2026-09-04T01:02:03Z"
    assert dispatched[0][2] == 15


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


def test_tool_can_report_confirmed_failure_after_dispatch() -> None:
    manager = ToolManager()
    manager.register(ConfirmedFailureTool())
    executor = CapabilityExecutor(SkillManager(), manager)
    context = _context()
    context = AgentExecutionContext(
        agent_id=context.agent_id,
        agent_role=context.agent_role,
        parent_agent_id=context.parent_agent_id,
        task_id=context.task_id,
        memory_scope=context.memory_scope,
        capability_scope=CapabilityScope("main_agent", (), ("confirmed_failure",)),
    )

    result = executor.execute(
        ExecutionDecision(
            CALL_TOOL,
            "confirmed_failure",
            {"value": "hello"},
            "Exercise confirmed failure.",
        ),
        context,
        Task("task-metadata"),
    )

    assert result.failure is not None
    assert result.failure.code == "tool_execution_failed"
    assert result.uncertain is False
