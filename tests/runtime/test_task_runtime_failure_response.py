from dataclasses import replace
from datetime import datetime, timezone

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from runtime.task_runtime import TaskRuntime
from sessions.execution_state import ToolFailureKind, ToolFailureObservation
from sessions.session_manager import TaskSessionManager


def test_runtime_collects_step_failures_for_completion_context():
    runtime = TaskRuntime(
        session_manager=TaskSessionManager(
            session_id_factory=lambda: "session-failure-response",
            task_id_factory=lambda: "task-failure-response",
        )
    )
    handle = runtime.submit(
        HandoffRequest(
            task_goal="Inspect the scene.",
            trigger_event=StandardizedEvent(
                trace_id="trace-failure-response",
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
    )
    session = runtime.get_session(handle.task_id)
    failure = ToolFailureObservation(
        attempt_id="step1_try",
        tool_name="camera_scene",
        kind=ToolFailureKind.PERMISSION_DENIED,
        code="permission_denied",
        message="camera permission was denied",
        arguments={},
        retryable=False,
    )
    session.step_history = (
        replace(session.current_step, failures=(failure,)),
    )

    assert runtime._execution_failures(session) == (failure,)
