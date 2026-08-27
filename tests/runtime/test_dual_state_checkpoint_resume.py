from datetime import datetime, timezone
import json

from agent.context import AgentExecutionContext, CapabilityScope
from events import StandardizedEvent
from runtime.task_store import CHECKPOINT_SCHEMA_VERSION, TaskStore
from tasks.task import Task, TaskIntent, TaskState


def _task() -> Task:
    event = StandardizedEvent(
        trace_id="trace-resume-verification",
        source="test",
        payload={"text": "Create a report"},
        event_type="USER_UTTERANCE",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        metadata={},
    )
    context = AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-resume-verification",
        trace_id=event.trace_id,
        handoff_goal="Create a report",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ()),
    )
    return Task(
        task_id=context.task_id,
        trace_id=event.trace_id,
        source_event=event,
        execution_context=context,
        state=TaskState.REASONING,
        first_decision_completed=True,
        intent=TaskIntent(
            "Create a report",
            deliverables=("report.md",),
            minimum_acceptance_criteria=("The report exists.",),
        ),
        task_local_state={
            "pending_reasoning": {"purpose": "verification"},
            "verification_in_progress": True,
            "verification_round": 1,
            "draft_final_response": "The report is ready.",
            "verification_results": (
                {"tool_name": "artifact_exists", "payload": {"exists": True}},
            ),
        },
    )


def test_checkpoint_preserves_verification_continuation(tmp_path) -> None:
    store = TaskStore(tmp_path)
    task = _task()

    store.save(task)
    restored = store.load(task.task_id)

    assert restored is not None
    assert restored.task.intent == task.intent
    assert restored.task.first_decision_completed
    assert restored.task.task_local_state["pending_reasoning"] == {
        "purpose": "verification"
    }
    assert restored.task.task_local_state["verification_round"] == 1
    assert restored.task.task_local_state["draft_final_response"] == (
        "The report is ready."
    )
    assert restored.task.task_local_state["verification_results"][0][
        "payload"
    ]["exists"] is True


def test_old_checkpoint_schema_is_not_migrated(tmp_path) -> None:
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps({"schema_version": CHECKPOINT_SCHEMA_VERSION - 1, "version": 1}),
        encoding="utf-8",
    )

    assert TaskStore(tmp_path).load("legacy") is None
