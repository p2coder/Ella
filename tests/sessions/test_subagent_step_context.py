from dataclasses import replace
from datetime import datetime, timezone

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from events import StandardizedEvent
from sessions.decision import CALL_TOOL
from sessions.execution_state import ToolFailureKind, ToolFailureObservation
from sessions.session import TaskSession
from sessions.subagent import SubAgent
from skill import SkillManager
from tools.base import ToolDefinition


def make_session():
    handoff = HandoffRequest(
        task_goal="Inspect the current scene.",
        trigger_event=StandardizedEvent(
            trace_id="trace-step-context",
            source="test",
            timestamp=datetime(2026, 7, 2, tzinfo=timezone.utc),
            payload={"text": "Look at the scene"},
            event_type="USER_UTTERANCE",
        ),
        user_preference_summary="",
        environment_summary="",
        context_summary="",
        constraints=(),
        completion_criteria=("Done.",),
    )
    return TaskSession("session-step", "task-step", handoff)


def definition(name):
    return ToolDefinition(
        name=name,
        description=f"Use {name}.",
        schema_version="1",
        input_schema={"type": "object"},
        input_examples=({},),
        output_schema={"type": "object"},
    )


def failure(attempt_id="step1_try"):
    return ToolFailureObservation(
        attempt_id=attempt_id,
        tool_name="camera_scene",
        kind=ToolFailureKind.INVALID_ARGUMENTS,
        code="invalid_tool_input",
        message="max_frames must be a number",
        arguments={"max_frames": "many"},
        retryable=True,
    )


def test_step_context_separates_successes_and_failures():
    session = make_session()
    session.tool_trace = (
        {
            "tool_name": "weather",
            "payload": {"status": "available", "summary": "Sunny"},
        },
    )
    session.current_step = replace(
        session.current_step,
        retry_index=1,
        active_tool_name="camera_scene",
        blacklisted_tools=("screen_scene",),
        failures=(failure(),),
    )

    context = SubAgent(SkillManager())._execution_step_context(session)

    assert context["attempt_id"] == "step1_retry1"
    assert context["repair_mode"] is True
    assert context["active_tool_name"] == "camera_scene"
    assert context["blacklisted_tools"] == ("screen_scene",)
    assert context["successful_tool_results"] == session.tool_trace
    assert context["failure_observations"][0]["code"] == "invalid_tool_input"


def test_repair_mode_exposes_only_active_tool():
    session = make_session()
    session.current_step = replace(
        session.current_step,
        retry_index=1,
        active_tool_name="camera_scene",
        failures=(failure(),),
    )
    subagent = SubAgent(SkillManager())

    filtered = subagent._filter_definitions_for_step(
        (definition("camera_scene"), definition("weather")),
        session,
    )

    assert tuple(item.name for item in filtered) == ("camera_scene",)


def test_repair_tool_switch_remains_detectable():
    subagent = SubAgent(SkillManager())

    decision = subagent._decision_from_payload(
        {
            "action": "CALL_TOOL",
            "tool_name": "weather",
            "arguments": {},
            "reason": "Switch tools.",
        },
        (
            {
                "name": "camera_scene",
                "input_schema": {"type": "object"},
            },
        ),
        repair_active_tool="camera_scene",
    )

    assert decision.action == CALL_TOOL
    assert decision.tool_name == "weather"


def test_successful_camera_observation_hides_camera_for_rest_of_task():
    session = make_session()
    session.tool_trace = (
        {
            "tool_name": "camera_scene",
            "payload": {
                "status": "available",
                "summary": "The requested object is not clearly visible.",
            },
        },
    )
    subagent = SubAgent(SkillManager())

    filtered = subagent._filter_definitions_for_step(
        (definition("camera_scene"), definition("weather")),
        session,
    )

    assert tuple(item.name for item in filtered) == ("weather",)


def test_failed_camera_observation_does_not_count_as_success():
    session = make_session()
    session.tool_trace = (
        {
            "tool_name": "camera_scene",
            "payload": {
                "status": "unavailable",
                "error": {"code": "permission_denied"},
            },
        },
    )
    subagent = SubAgent(SkillManager())

    filtered = subagent._filter_definitions_for_step(
        (definition("camera_scene"),),
        session,
    )

    assert tuple(item.name for item in filtered) == ("camera_scene",)


def test_non_retryable_failure_hides_tool_from_later_steps():
    session = make_session()
    denied = ToolFailureObservation(
        attempt_id="step1_try",
        tool_name="camera_scene",
        kind=ToolFailureKind.PERMISSION_DENIED,
        code="permission_denied",
        message="camera permission denied",
        arguments={},
        retryable=False,
    )
    session.step_history = (
        replace(session.current_step, failures=(denied,)),
    )
    session.current_step = replace(session.current_step, step_number=2)
    subagent = SubAgent(SkillManager())

    filtered = subagent._filter_definitions_for_step(
        (definition("camera_scene"), definition("weather")),
        session,
    )

    assert tuple(item.name for item in filtered) == ("weather",)
