from datetime import datetime, timezone
from pathlib import Path

from agent.handoff import HandoffRequest
from agent.strategy import StrategyDecision
from events import StandardizedEvent
from runtime.task_runtime import TaskRuntime
from skill import SkillManager
from tasks.factory import TaskFactory
from tasks.task import TaskState


def _handoff() -> HandoffRequest:
    event = StandardizedEvent(
        "trace", "test", datetime.now(timezone.utc),
        {"text": "hello"}, "USER_UTTERANCE", {},
    )
    return HandoffRequest("Reply to the user", event, "", "", "", (), ())


class StubSubAgent:
    skill_manager = SkillManager()

    def select_strategy(self, handoff, context, task):
        return StrategyDecision(
            "react", None, "direct execution", None,
            handoff.completion_criteria, task_id=task.task_id,
            trace_id=context.trace_id,
        )


class StubToolManager:
    def list_names(self):
        return ()


class StubExecutor:
    tool_manager = StubToolManager()


def test_task_state_contract_contains_only_canonical_states():
    assert set(TaskState.__members__) == {
        "CREATED",
        "FORMULATING",
        "READY",
        "RUNNING",
        "WAITING",
        "PAUSE_REQUESTED",
        "PAUSED",
        "KILL_REQUESTED",
        "SUCCEEDED",
        "FAILED",
        "UNCERTAIN",
        "KILLED",
        "DELIVERED",
    }


def test_preformulated_submission_is_ready_then_runs_directly():
    runtime = TaskRuntime(
        task_factory=TaskFactory(
            task_id_factory=lambda: "task",
        ),
        subagent=StubSubAgent(),
        executor=StubExecutor(),
    )
    handle = runtime.submit(_handoff())
    assert runtime.get_task(handle.task_id).state is TaskState.READY

    result = runtime.step(handle.task_id)
    assert result.task.state is TaskState.RUNNING
    assert result.task.current_strategy.mode == "react"


def test_replan_is_running_internal_state_not_task_state():
    source = Path("runtime/task_runtime.py").read_text(encoding="utf-8")
    assert "TaskState.PLANNING" not in source
    assert "TaskState.REPLANNING" not in source
    assert "TaskState.COMPLETED" not in source
    assert "TaskState.CANCELLED" not in source
    assert 'task_local_state["replan_requested"]' in source
