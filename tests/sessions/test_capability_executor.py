from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from events import StandardizedEvent
from sessions.decision import (
    CALL_TOOL,
    COMPLETE,
    REPLAN,
    WAIT,
    ExecutionDecision,
)
from sessions.executor import CapabilityExecutor
from sessions.session import TaskSession
from sessions.strategy import StrategyDecision
from skill import SkillDefinition, SkillManager
from tools import ToolManager, ToolResult


@dataclass
class RecordingTool:
    name: str
    calls: int = 0

    def run(self, context: AgentExecutionContext) -> ToolResult:
        self.calls += 1
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            session_id=context.session_id,
            trace_id=context.trace_id,
            payload={"calls": self.calls},
        )


def make_handoff() -> HandoffRequest:
    return HandoffRequest(
        task_goal="Give the user a short reminder before leaving.",
        trigger_event=StandardizedEvent(
            trace_id="trace-executor",
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
        session_id="session-executor",
        task_id="task-executor",
        trace_id="trace-executor",
        handoff_goal="Give the user a short reminder before leaving.",
        memory_scope="task_local",
        allowed_tools=allowed_tools,
        permissions=(),
    )


def make_session() -> TaskSession:
    return TaskSession(
        session_id="session-executor",
        task_id="task-executor",
        handoff=make_handoff(),
    )


def make_strategy(skill_name: str | None = "going_out") -> StrategyDecision:
    return StrategyDecision(
        mode="skill" if skill_name else "plan_to_execute",
        skill_name=skill_name,
        reason="Use the selected strategy.",
        initial_plan=None,
        completion_criteria=("A reminder is ready.",),
        session_id="session-executor",
        task_id="task-executor",
        trace_id="trace-executor",
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


def make_executor(
    tool_manager: ToolManager,
    skill_manager: SkillManager | None = None,
) -> CapabilityExecutor:
    return CapabilityExecutor(
        skill_manager=skill_manager or make_skill_manager(),
        tool_manager=tool_manager,
    )


def call_tool_decision(tool_name: str) -> ExecutionDecision:
    return ExecutionDecision(
        action=CALL_TOOL,
        tool_name=tool_name,
        tool_input=None,
        reason="Collect one required input.",
        is_complete=False,
    )


def test_call_tool_executes_exactly_one_selected_tool():
    selected = RecordingTool("selected")
    unselected = RecordingTool("unselected")
    tool_manager = ToolManager()
    tool_manager.register(selected)
    tool_manager.register(unselected)

    result = make_executor(tool_manager).execute(
        decision=call_tool_decision("selected"),
        strategy=make_strategy(),
        context=make_context(("selected", "unselected")),
        task_session=make_session(),
    )

    assert result.tool_result is not None
    assert result.tool_result.tool_name == "selected"
    assert selected.calls == 1
    assert unselected.calls == 0
    assert result.replan_required is False


def test_tool_outside_allowed_tools_is_rejected_without_execution():
    tool = RecordingTool("selected")
    tool_manager = ToolManager()
    tool_manager.register(tool)

    result = make_executor(tool_manager).execute(
        decision=call_tool_decision("selected"),
        strategy=make_strategy(),
        context=make_context(()),
        task_session=make_session(),
    )

    assert result.tool_result is None
    assert result.replan_required is True
    assert result.failure_reason == "tool selected is not allowed"
    assert tool.calls == 0


def test_missing_or_removed_tool_requires_replanning():
    tool_manager = ToolManager()
    tool_manager.register(RecordingTool("selected"))
    tool_manager.unregister("selected")

    result = make_executor(tool_manager).execute(
        decision=call_tool_decision("selected"),
        strategy=make_strategy(),
        context=make_context(("selected",)),
        task_session=make_session(),
    )

    assert result.tool_result is None
    assert result.replan_required is True
    assert result.failure_reason == "tool selected is not registered"


def test_missing_or_removed_skill_requires_replanning():
    tool = RecordingTool("selected")
    tool_manager = ToolManager()
    tool_manager.register(tool)

    result = make_executor(tool_manager, SkillManager()).execute(
        decision=call_tool_decision("selected"),
        strategy=make_strategy(),
        context=make_context(("selected",)),
        task_session=make_session(),
    )

    assert result.tool_result is None
    assert result.replan_required is True
    assert result.failure_reason == "skill going_out is not registered"
    assert tool.calls == 0


@pytest.mark.parametrize(
    ("action", "is_complete", "replan_required"),
    (
        (COMPLETE, True, False),
        (WAIT, False, False),
        (REPLAN, False, True),
    ),
)
def test_non_tool_actions_do_not_call_tools(
    action: str,
    is_complete: bool,
    replan_required: bool,
):
    tool = RecordingTool("selected")
    tool_manager = ToolManager()
    tool_manager.register(tool)

    result = make_executor(tool_manager).execute(
        decision=ExecutionDecision(
            action=action,
            tool_name=None,
            tool_input=None,
            reason="No tool call is needed.",
            is_complete=is_complete,
        ),
        strategy=make_strategy(),
        context=make_context(("selected",)),
        task_session=make_session(),
    )

    assert result.tool_result is None
    assert result.replan_required is replan_required
    assert tool.calls == 0


def test_executor_does_not_mutate_task_session():
    tool = RecordingTool("selected")
    tool_manager = ToolManager()
    tool_manager.register(tool)
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

    make_executor(tool_manager).execute(
        decision=call_tool_decision("selected"),
        strategy=make_strategy(),
        context=make_context(("selected",)),
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
