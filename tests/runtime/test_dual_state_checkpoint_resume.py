from datetime import datetime, timezone
import json

from agent.context import AgentExecutionContext, CapabilityScope
from events import StandardizedEvent
import pytest

from runtime.task_store import (
    CHECKPOINT_SCHEMA_VERSION,
    TaskStore,
    UnsupportedCheckpointSchema,
)
from tasks.task import Task, TaskIntent, TaskState


def _task() -> Task:
    event = StandardizedEvent(
        task_id="task-resume-verification",
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
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ()),
    )
    return Task(
        task_id=context.task_id,
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
            "pending_reasoning": {"purpose": "execution"},
            "draft_final_response": "The report is ready.",
        },
    )


def test_checkpoint_preserves_reasoning_state_without_verification_continuation(
    tmp_path,
) -> None:
    store = TaskStore(tmp_path)
    task = _task()

    store.save(task)
    restored = store.load(task.task_id)

    assert restored is not None
    assert restored.task.intent == task.intent
    assert restored.task.first_decision_completed
    assert restored.task.task_local_state["pending_reasoning"] == {
        "purpose": "execution"
    }
    assert restored.task.task_local_state["draft_final_response"] == (
        "The report is ready."
    )
    assert "verification_in_progress" not in restored.task.task_local_state
    assert "verification_round" not in restored.task.task_local_state
    assert "verification_results" not in restored.task.task_local_state


def test_old_checkpoint_schema_is_explicitly_rejected(tmp_path) -> None:
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps({"schema_version": CHECKPOINT_SCHEMA_VERSION - 1, "version": 1}),
        encoding="utf-8",
    )

    with pytest.raises(
        UnsupportedCheckpointSchema,
        match="old version cannot be restored",
    ):
        TaskStore(tmp_path).load("legacy")
