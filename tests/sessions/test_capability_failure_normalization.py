from dataclasses import dataclass
from datetime import datetime, timezone

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from events import StandardizedEvent
from sessions.decision import CALL_TOOL, ExecutionDecision
from sessions.execution_state import ToolFailureKind
from sessions.executor import CapabilityExecutor
from sessions.session import TaskSession
from sessions.strategy import StrategyDecision
from skill import SkillManager
from tools.base import ToolDefinition, ToolResult
from tools.manager import ToolManager


@dataclass
class ResultTool:
    payload: dict
    name: str = "result_tool"
    allowed_roles: tuple[str, ...] = ("main_agent",)
    calls: int = 0

    @property
    def definition(self):
        return ToolDefinition(
            name=self.name,
            description="Return a configured test payload.",
            schema_version="1",
            input_schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            input_examples=({"value": "ok"},),
            output_schema={"type": "object"},
        )

    def run(self, context, arguments=None):
        self.calls += 1
        return ToolResult(
            self.name,
            context.task_id,
            context.session_id,
            context.trace_id,
            self.payload,
        )


@dataclass
class RaisingTool(ResultTool):
    def run(self, context, arguments=None):
        self.calls += 1
        raise RuntimeError("internal secret detail")


def make_runtime_parts(tool, *, allowed=True):
    manager = ToolManager()
    manager.register(tool)
    handoff = HandoffRequest(
        task_goal="Test tool failure normalization.",
        trigger_event=StandardizedEvent(
            trace_id="trace-failure",
            source="test",
            timestamp=datetime(2026, 7, 2, tzinfo=timezone.utc),
            payload={"text": "test"},
            event_type="USER_UTTERANCE",
        ),
        user_preference_summary="",
        environment_summary="",
        context_summary="",
        constraints=(),
        completion_criteria=("Done.",),
    )
    context = AgentExecutionContext(
        agent_id="ella",
        agent_role="main_agent",
        parent_agent_id=None,
        session_id="session-failure",
        task_id="task-failure",
        trace_id="trace-failure",
        handoff_goal=handoff.task_goal,
        memory_scope="task_local",
        allowed_tools=(tool.name,) if allowed else (),
    )
    session = TaskSession(context.session_id, context.task_id, handoff)
    strategy = StrategyDecision("react", None, "test", None, ("Done.",))
    decision = ExecutionDecision(
        CALL_TOOL,
        tool.name,
        {"value": "ok"},
        "test",
        False,
    )
    executor = CapabilityExecutor(SkillManager(), manager)
    return executor, decision, strategy, context, session


def execute(tool, *, allowed=True, arguments=None):
    executor, decision, strategy, context, session = make_runtime_parts(
        tool,
        allowed=allowed,
    )
    if arguments is not None:
        decision = ExecutionDecision(
            CALL_TOOL,
            tool.name,
            arguments,
            "test",
            False,
        )
    return executor.execute(decision, strategy, context, session)


def test_success_returns_only_tool_result():
    result = execute(ResultTool({"status": "available", "items": []}))

    assert result.tool_result is not None
    assert result.failure is None


def test_invalid_input_returns_retryable_failure_without_calling_tool():
    tool = ResultTool({"status": "available"})
    result = execute(tool, arguments={})

    assert tool.calls == 0
    assert result.tool_result is None
    assert result.failure.kind is ToolFailureKind.INVALID_ARGUMENTS
    assert result.failure.retryable is True


def test_permission_rejection_is_normalized():
    result = execute(ResultTool({"status": "available"}), allowed=False)

    assert result.tool_result is None
    assert result.failure.kind is ToolFailureKind.PERMISSION_DENIED


def test_unavailable_legacy_result_is_normalized_and_retained_as_raw_only():
    result = execute(
        ResultTool(
            {
                "status": "unavailable",
                "error": {
                    "code": "backend_unavailable",
                    "message": "camera backend unavailable",
                },
            }
        )
    )

    assert result.tool_result is None
    assert result.failure.kind is ToolFailureKind.ENVIRONMENT_UNAVAILABLE
    assert result.failure.code == "backend_unavailable"
    assert isinstance(result.raw_result, ToolResult)
    assert "raw_result" not in repr(result)


def test_permission_denied_legacy_result_maps_to_permission_failure():
    result = execute(
        ResultTool(
            {
                "status": "unavailable",
                "error": {
                    "code": "permission_denied",
                    "message": "camera permission denied",
                },
            }
        )
    )

    assert result.failure.kind is ToolFailureKind.PERMISSION_DENIED


def test_tool_exception_becomes_internal_failure():
    result = execute(RaisingTool({}))

    assert result.tool_result is None
    assert result.failure.kind is ToolFailureKind.TOOL_EXECUTION_FAILED
    assert result.failure.retryable is False


def test_successful_negative_business_result_remains_success():
    result = execute(
        ResultTool(
            {
                "status": "available",
                "summary": "The requested object is not visible.",
                "visible_items": [],
            }
        )
    )

    assert result.tool_result.payload["visible_items"] == []
    assert result.failure is None
