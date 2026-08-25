from datetime import datetime, timezone

from agent.context import AgentExecutionContext, CapabilityScope
from agent.verification import VerificationAgent, VerificationVerdict
from events import StandardizedEvent
from tasks.task import Task, TaskGoalState, TaskIntent, TaskState


def _task(*, draft: str = "A clear answer.") -> Task:
    event = StandardizedEvent(
        trace_id="trace-verification",
        source="test",
        payload={"text": "Answer this request"},
        event_type="USER_UTTERANCE",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        metadata={},
    )
    context = AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-verification",
        trace_id=event.trace_id,
        handoff_goal="Answer this request",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ()),
    )
    return Task(
        task_id=context.task_id,
        trace_id=event.trace_id,
        source_event=event,
        execution_context=context,
        state=TaskState.REASONING,
        intent=TaskIntent(
            goal="Answer this request",
            deliverables=("A user-facing answer",),
            minimum_acceptance_criteria=("The answer addresses the request",),
        ),
        task_local_state={"draft_final_response": draft},
    )


def test_deterministic_verifier_checks_actual_draft() -> None:
    verdict = VerificationAgent().verify(_task())

    assert verdict.goal_state is TaskGoalState.ACHIEVED
    assert verdict.recoverable is False


def test_empty_draft_is_not_achieved_and_recoverable() -> None:
    verdict = VerificationAgent().verify(_task(draft=""))

    assert verdict.goal_state is TaskGoalState.NOT_ACHIEVED
    assert verdict.recoverable is True
    assert verdict.draft_quality_issues


def test_verdict_serialization_uses_three_value_goal_state() -> None:
    verdict = VerificationVerdict(
        TaskGoalState.PARTIALLY_ACHIEVED,
        ("One criterion passed.",),
        ("One deliverable is missing.",),
        ("Draft must disclose the missing deliverable.",),
        False,
        "",
        "The goal was partially achieved.",
    )

    assert verdict.to_dict()["goal_state"] == "partially_achieved"
