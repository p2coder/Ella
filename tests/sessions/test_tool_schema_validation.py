from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from events import StandardizedEvent
from sessions.decision import CALL_TOOL, COMPLETE, REPLAN, WAIT, ExecutionDecision
from sessions.executor import CapabilityExecutor
from sessions.session import TaskSession
from sessions.strategy import StrategyDecision
from skill import SkillDefinition, SkillManager
from tools.base import ToolDefinition, ToolResult
from tools.manager import ToolManager
from tools.mock_tools import MockChecklistTool


def make_handoff() -> HandoffRequest:
    return HandoffRequest(
        task_goal="Give the user a short reminder before leaving.",
        trigger_event=StandardizedEvent(
            trace_id="trace-schema",
            source="cli_input",
            timestamp=datetime(2026, 6, 13, 14, 0, tzinfo=timezone.utc),
            payload={"text": "Ella，我要出门了"},
            event_type="USER_UTTERANCE",
            metadata={"trigger_kind": "user_initiated"},
        ),
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Mock environment only.",
        context_summary="User is leaving.",
        constraints=("Keep it short.",),
        completion_criteria=("A reminder is ready.",),
    )


def make_context(allowed_tools: tuple[str, ...]) -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        session_id="session-schema",
        task_id="task-schema",
        trace_id="trace-schema",
        handoff_goal="Give the user a short reminder before leaving.",
        memory_scope="task_local",
        allowed_tools=allowed_tools,
        permissions=(),
    )


def make_session() -> TaskSession:
    return TaskSession(
        session_id="session-schema",
        task_id="task-schema",
        handoff=make_handoff(),
    )


def make_strategy() -> StrategyDecision:
    return StrategyDecision(
        mode="skill",
        skill_name="going_out",
        reason="Use the selected strategy.",
        initial_plan=None,
        completion_criteria=("A reminder is ready.",),
        session_id="session-schema",
        task_id="task-schema",
        trace_id="trace-schema",
    )


def make_skill_manager() -> SkillManager:
    manager = SkillManager()
    manager.register(
        SkillDefinition(
            name="going_out",
            description="Prepare a concise reminder before leaving.",
            when_to_use="Use when the user is heading out.",
            path=Path("skill/skills/going_out/SKILL.md"),
        )
    )
    return manager


def make_executor(tool_manager: ToolManager) -> CapabilityExecutor:
    return CapabilityExecutor(
        skill_manager=make_skill_manager(),
        tool_manager=tool_manager,
    )


def call_tool_decision(
    tool_name: str,
    tool_input: dict[str, object] | None,
) -> ExecutionDecision:
    return ExecutionDecision(
        action=CALL_TOOL,
        tool_name=tool_name,
        tool_input=tool_input,
        reason="Collect one required input.",
        is_complete=False,
    )


def test_valid_call_tool_input_executes_one_tool() -> None:
    tool = SchemaTool()
    manager = ToolManager()
    manager.register(tool)

    result = make_executor(manager).execute(
        decision=call_tool_decision(
            "schema_tool",
            {"location": "Tokyo", "unit": "celsius", "items": ["keys"]},
        ),
        strategy=make_strategy(),
        context=make_context(("schema_tool",)),
        task_session=make_session(),
    )

    assert tool.calls == 1
    assert result.replan_required is False
    assert result.tool_result == ToolResult(
        tool_name="schema_tool",
        task_id="task-schema",
        session_id="session-schema",
        trace_id="trace-schema",
        payload={
            "summary": "Validated tool output.",
            "confidence": 0.9,
            "ok": True,
        },
    )


def test_invalid_input_does_not_call_tool() -> None:
    tool = SchemaTool()
    manager = ToolManager()
    manager.register(tool)

    result = make_executor(manager).execute(
        decision=call_tool_decision(
            "schema_tool",
            {"location": "Tokyo", "unit": "kelvin"},
        ),
        strategy=make_strategy(),
        context=make_context(("schema_tool",)),
        task_session=make_session(),
    )

    assert tool.calls == 0
    assert result.tool_result is None
    assert result.tool_results == ()
    assert result.replan_required is True
    assert "invalid_tool_input" in result.failure_reason


def test_unknown_tool_does_not_execute() -> None:
    result = make_executor(ToolManager()).execute(
        decision=call_tool_decision("missing_tool", {}),
        strategy=make_strategy(),
        context=make_context(("missing_tool",)),
        task_session=make_session(),
    )

    assert result.tool_result is None
    assert result.replan_required is True
    assert result.unavailable_tool == "missing_tool"
    assert "not registered" in result.failure_reason


def test_removed_tool_returns_replan_required() -> None:
    manager = ToolManager()
    manager.register(SchemaTool())
    manager.unregister("schema_tool")

    result = make_executor(manager).execute(
        decision=call_tool_decision("schema_tool", {}),
        strategy=make_strategy(),
        context=make_context(("schema_tool",)),
        task_session=make_session(),
    )

    assert result.tool_result is None
    assert result.replan_required is True
    assert result.unavailable_tool == "schema_tool"


def test_invalid_output_returns_invalid_tool_output_without_success_trace() -> None:
    manager = ToolManager()
    manager.register(BadOutputTool())
    session = make_session()

    result = make_executor(manager).execute(
        decision=call_tool_decision("bad_output", {}),
        strategy=make_strategy(),
        context=make_context(("bad_output",)),
        task_session=session,
    )

    assert result.tool_result is None
    assert result.tool_results == ()
    assert result.replan_required is True
    assert "invalid_tool_output" in result.failure_reason
    assert session.tool_trace == ()


def test_complete_wait_and_replan_do_not_call_tools() -> None:
    tool = SchemaTool()
    manager = ToolManager()
    manager.register(tool)

    for action, is_complete in (
        (COMPLETE, True),
        (WAIT, False),
        (REPLAN, False),
    ):
        result = make_executor(manager).execute(
            decision=ExecutionDecision(
                action=action,
                tool_name=None,
                tool_input=None,
                reason="No tool call is needed.",
                is_complete=is_complete,
            ),
            strategy=make_strategy(),
            context=make_context(("schema_tool",)),
            task_session=make_session(),
        )
        assert result.tool_result is None

    assert tool.calls == 0


def test_existing_tools_remain_compatible_with_empty_arguments() -> None:
    manager = ToolManager()
    manager.register(MockChecklistTool())

    result = make_executor(manager).execute(
        decision=call_tool_decision("mock_checklist", {}),
        strategy=make_strategy(),
        context=make_context(("mock_checklist",)),
        task_session=make_session(),
    )

    assert result.tool_result is not None
    assert result.tool_result.payload == {
        "items": ("phone", "keys", "wallet", "umbrella")
    }


def test_existing_context_only_tools_ignore_legacy_context_arguments() -> None:
    manager = ToolManager()
    manager.register(MockChecklistTool())

    result = make_executor(manager).execute(
        decision=call_tool_decision(
            "mock_checklist",
            {"task_goal": "Prepare a reminder.", "session_id": "session-schema"},
        ),
        strategy=make_strategy(),
        context=make_context(("mock_checklist",)),
        task_session=make_session(),
    )

    assert result.replan_required is False
    assert result.tool_result is not None
    assert result.tool_result.payload == {
        "items": ("phone", "keys", "wallet", "umbrella")
    }


def test_executor_does_not_mutate_task_session_state() -> None:
    manager = ToolManager()
    manager.register(SchemaTool())
    session = make_session()
    before = (
        session.state,
        dict(session.task_local_state),
        session.message_history,
        session.tool_trace,
        session.current_strategy,
        session.completion,
        session.failure_reason,
    )

    make_executor(manager).execute(
        decision=call_tool_decision("schema_tool", {"location": "Tokyo"}),
        strategy=make_strategy(),
        context=make_context(("schema_tool",)),
        task_session=session,
    )

    after = (
        session.state,
        dict(session.task_local_state),
        session.message_history,
        session.tool_trace,
        session.current_strategy,
        session.completion,
        session.failure_reason,
    )
    assert after == before


@dataclass(slots=True)
class SchemaTool:
    name: str = "schema_tool"
    allowed_roles: tuple[str, ...] = ("main_agent",)
    calls: int = 0

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Use for schema validation tests. Do not use as a real "
                "capability."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                    },
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["location"],
                "additionalProperties": False,
            },
            input_examples=({"location": "Tokyo", "unit": "celsius"},),
            output_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "confidence": {"type": "number"},
                    "ok": {"type": "boolean"},
                },
                "required": ["summary", "confidence", "ok"],
                "additionalProperties": False,
            },
        )

    def run(self, context: AgentExecutionContext) -> ToolResult:
        self.calls += 1
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            session_id=context.session_id,
            trace_id=context.trace_id,
            payload={
                "summary": "Validated tool output.",
                "confidence": 0.9,
                "ok": True,
            },
        )


@dataclass(slots=True)
class BadOutputTool:
    name: str = "bad_output"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Use for invalid output tests. Do not use as a real capability."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            input_examples=({},),
            output_schema={
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
                "additionalProperties": False,
            },
        )

    def run(self, context: AgentExecutionContext) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            session_id=context.session_id,
            trace_id=context.trace_id,
            payload={"unexpected": True},
        )
