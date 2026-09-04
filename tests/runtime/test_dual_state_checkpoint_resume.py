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
from runtime.task_runtime import TaskRuntime
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


def test_runtime_persists_workflow_progress_by_task_id(tmp_path) -> None:
    store = TaskStore(tmp_path)
    runtime = TaskRuntime(task_store=store)
    task = _task()
    runtime._tasks[task.task_id] = task

    runtime.record_workflow_progress(
        task.task_id,
        {
            "status": "running",
            "script": "return 1;",
            "active_tool_count": 0,
            "child_results": (),
        },
    )

    restored = store.load(task.task_id)
    assert restored is not None
    assert restored.task.task_local_state["workflow_execution"] == {
        "status": "running",
        "script": "return 1;",
        "active_tool_count": 0,
        "child_results": [],
    }


def test_runtime_persists_child_progress_by_agent_id(tmp_path) -> None:
    store = TaskStore(tmp_path)
    runtime = TaskRuntime(task_store=store)
    task = _task()
    runtime._tasks[task.task_id] = task

    runtime.record_child_progress(
        task.task_id,
        {
            "child_agent_id": "agent-child",
            "parent_agent_id": "ella-main",
            "status": "running",
            "in_flight_action": {"tool_name": "edit"},
        },
    )

    restored = store.load(task.task_id)
    assert restored is not None
    child = restored.task.task_local_state["child_executions"]["agent-child"]
    assert child["parent_agent_id"] == "ella-main"
    assert child["in_flight_action"] == {"tool_name": "edit"}


def test_runtime_isolates_old_checkpoint_and_reports_recovery_error(tmp_path) -> None:
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps({"schema_version": CHECKPOINT_SCHEMA_VERSION - 1, "version": 1}),
        encoding="utf-8",
    )
    runtime = TaskRuntime(task_store=TaskStore(tmp_path))

    runtime._restore_from_checkpoints()

    assert runtime.recovery_errors[0]["task_id"] == "legacy"
    assert runtime.recovery_errors[0]["code"] == "unsupported_checkpoint_schema"
