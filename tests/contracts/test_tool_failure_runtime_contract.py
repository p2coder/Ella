from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from prompts.templates import EXECUTION_DECISION_TEMPLATE
from runtime.task_runtime import TaskRuntime
from sessions.decision import CALL_TOOL, ExecutionDecision
from sessions.execution_state import (
    StepExecutionState,
    ToolFailureKind,
    ToolFailureObservation,
)
from sessions.executor import CapabilityExecutionResult
from sessions.session import TaskSession
from sessions.strategy import StrategyDecision
from sessions.subagent import SubAgent
from skill import SkillManager
from tools.base import ToolDefinition, ToolResult


def handoff(suffix="contract"):
    return HandoffRequest(
        task_goal="Inspect the current scene.",
        trigger_event=StandardizedEvent(
            trace_id=f"trace-{suffix}",
            source="test",
            timestamp=datetime(2026, 7, 2, tzinfo=timezone.utc),
            payload={"text": "inspect"},
            event_type="USER_UTTERANCE",
        ),
        user_preference_summary="",
        environment_summary="",
        context_summary="",
        constraints=(),
        completion_criteria=("Done.",),
    )


def definition(name):
    return ToolDefinition(
        name,
        f"Use {name}.",
        "1",
        {"type": "object"},
        ({},),
        {"type": "object"},
    )


def failure():
    return ToolFailureObservation(
        "step1_try",
        "camera_scene",
        ToolFailureKind.PERMISSION_DENIED,
        "permission_denied",
        "camera permission was denied",
        {},
        False,
    )


def test_success_and_failure_are_mutually_exclusive():
    decision = ExecutionDecision(CALL_TOOL, "camera_scene", {}, "test", False)
    strategy = StrategyDecision("react", None, "test", None, ("Done.",))
    result = ToolResult(
        "camera_scene",
        "task",
        "session",
        "trace",
        {"status": "available"},
    )

    with pytest.raises(ValueError, match="mutually exclusive"):
        CapabilityExecutionResult(
            decision,
            strategy,
            result,
            False,
            failure=failure(),
        )


def test_task_sessions_do_not_share_step_state():
    first = TaskSession("session-1", "task-1", handoff("one"))
    second = TaskSession("session-2", "task-2", handoff("two"))

    first.current_step = replace(
        first.current_step,
        blacklisted_tools=("camera_scene",),
        failures=(failure(),),
    )

    assert second.current_step == StepExecutionState()
    assert second.current_step is not first.current_step


def test_repair_switch_is_detected_before_execution():
    runtime = TaskRuntime()
    session = TaskSession("session", "task", handoff())
    session.current_step = replace(
        session.current_step,
        retry_index=1,
        active_tool_name="camera_scene",
    )
    switched = ExecutionDecision(CALL_TOOL, "weather", {}, "switch", False)

    violation = runtime._repair_violation(session, switched)

    assert violation is not None
    assert (
        violation.kind
        is ToolFailureKind.INVALID_ARGUMENTS_REPAIR_VIOLATION
    )
    assert violation.tool_name == "camera_scene"


def test_successful_insufficient_camera_observation_prevents_recapture():
    session = TaskSession("session", "task", handoff())
    session.tool_trace = (
        {
            "tool_name": "camera_scene",
            "payload": {
                "status": "available",
                "summary": "The requested object cannot be confirmed.",
                "visible_items": [],
            },
        },
    )
    subagent = SubAgent(SkillManager())

    visible = subagent._filter_definitions_for_step(
        (definition("camera_scene"), definition("weather")),
        session,
    )

    assert tuple(item.name for item in visible) == ("weather",)


def test_failed_camera_attempt_does_not_count_as_successful_observation():
    session = TaskSession("session", "task", handoff())
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

    visible = subagent._filter_definitions_for_step(
        (definition("camera_scene"),),
        session,
    )

    assert tuple(item.name for item in visible) == ("camera_scene",)


def test_raw_result_has_no_runtime_storage_path():
    runtime_source = Path("runtime/task_runtime.py").read_text()
    session_source = Path("sessions/session.py").read_text()

    assert "raw_result" not in runtime_source
    assert "raw_result" not in session_source


def test_retry_and_camera_policies_are_explicit():
    instruction = EXECUTION_DECISION_TEMPLATE.instruction

    assert "active_tool_name" in instruction
    assert "blacklisted_tools" in instruction
    assert "do not call camera_scene again" in instruction


def test_runtime_has_independent_argument_retry_budget():
    assert TaskRuntime().max_argument_retries == 2
    assert TaskRuntime(max_argument_retries=0).max_argument_retries == 0
