from datetime import datetime, timezone

from agent import MainAgent
from events import StandardizedEvent
from memory import MemoryManagementRequest
from sessions import SubAgent, TaskSessionManager
from sessions.completion import TaskCompletionPackage
from sessions.output import UserVisibleAgentOutput
from skill import SkillLoader, SkillManager
from tools import MockChecklistTool, MockWeatherTool


def make_execution_boundary():
    event = StandardizedEvent(
        trace_id="trace-context-contract",
        source="cli_input",
        timestamp=datetime(2026, 6, 13, 12, 30, tzinfo=timezone.utc),
        payload={"text": "Ella，我要出门了"},
        event_type="USER_UTTERANCE",
        metadata={"trigger_kind": "user_initiated"},
    )
    handoff = MainAgent().create_handoff(
        trigger_event=event,
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Mock environment context only.",
    )
    creation = TaskSessionManager(
        allowed_tools=("mock_weather", "mock_checklist"),
        permissions=("read_mock_context",),
        session_id_factory=lambda: "session-context-contract",
        task_id_factory=lambda: "task-context-contract",
    ).create_session(handoff)
    return handoff, creation


def test_context_ids_propagate_through_strategy_tools_completion_and_memory():
    handoff, creation = make_execution_boundary()
    skill_manager = SkillManager(loader=SkillLoader())
    skill_manager.refresh()
    strategy = SubAgent(skill_manager).select_strategy(
        handoff=handoff,
        context=creation.context,
        task_session=creation.session,
    )
    tool_results = (
        MockWeatherTool().run(creation.context),
        MockChecklistTool().run(creation.context),
    )
    completion = TaskCompletionPackage(
        context=creation.context,
        summary="Context propagation contract.",
        user_visible_output=UserVisibleAgentOutput(
            process={"strategy": strategy.skill_name},
            final_response="Take your keys and phone.",
        ),
        tool_results=tool_results,
    )
    request = MemoryManagementRequest.from_completion(completion)

    expected_ids = (
        "session-context-contract",
        "task-context-contract",
        "trace-context-contract",
    )
    assert (
        strategy.session_id,
        strategy.task_id,
        strategy.trace_id,
    ) == expected_ids
    for result in tool_results:
        assert (result.session_id, result.task_id, result.trace_id) == expected_ids
    assert (
        completion.context.session_id,
        completion.context.task_id,
        completion.context.trace_id,
    ) == expected_ids
    assert (request.session_id, request.task_id, request.trace_id) == expected_ids


def test_execution_context_preserves_handoff_and_permission_boundaries():
    handoff, creation = make_execution_boundary()
    context = creation.context

    assert creation.session.handoff is handoff
    assert context.handoff_goal == handoff.task_goal
    assert context.allowed_tools == ("mock_weather", "mock_checklist")
    assert context.permissions == ("read_mock_context",)
    assert context.memory_scope == "task_local"
    assert not hasattr(context, "tool_results")
    assert not hasattr(context, "selected_skill")
