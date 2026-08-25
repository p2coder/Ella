import pytest
from datetime import datetime, timezone

from agent.decision import CALL_TOOL, COMPLETE, ExecutionDecision
from events import StandardizedEvent
from prompts.engine import PromptEngine, PromptType
from runtime.executor import CapabilityExecutionResult
from runtime.task_runtime import TaskRuntime
from runtime.task_store import TaskStore
from tasks.factory import TaskFactory
from agent.handoff import HandoffRequest
from tasks.task import Task
from tasks.task import TaskState


def test_execution_protocol_has_only_call_tool_and_complete() -> None:
    assert {CALL_TOOL, COMPLETE} == {"CALL_TOOL", "COMPLETE"}
    with pytest.raises(ValueError, match="unsupported execution decision action"):
        ExecutionDecision("WAIT", None, None, "wait")
    with pytest.raises(ValueError, match="unsupported execution decision action"):
        ExecutionDecision("REPLAN", None, None, "replan")


def test_complete_requires_conclusion_and_keeps_evidence_separate() -> None:
    decision = ExecutionDecision(
        COMPLETE,
        None,
        None,
        "The available evidence is sufficient.",
        "The requested object is visible.",
        ("observation-1",),
    )

    assert decision.completion_summary == "The requested object is visible."
    assert decision.evidence_refs == ("observation-1",)
    assert decision.to_dict()["decision_reason"] != decision.completion_summary
    assert ExecutionDecision.from_dict(decision.to_dict()) == decision


def test_strategy_selection_prompt_is_removed() -> None:
    assert not hasattr(PromptType, "STRATEGY_SELECTION")
    with pytest.raises(ValueError, match="Unsupported prompt type"):
        PromptEngine().build("STRATEGY_SELECTION", {})


def test_runtime_states_use_reasoning_and_tool_execution() -> None:
    assert TaskState.REASONING.value == "reasoning"
    assert TaskState.TOOL_EXECUTION.value == "tool_execution"
    assert "running" not in {state.value for state in TaskState}
    assert "waiting" not in {state.value for state in TaskState}


def test_post_reasoning_decision_survives_checkpoint(tmp_path) -> None:
    event = StandardizedEvent(
        trace_id="trace-1",
        source="test",
        payload={"text": "hello"},
        event_type="USER_UTTERANCE",
        timestamp=datetime.now(timezone.utc),
    )
    decision = ExecutionDecision(
        COMPLETE,
        None,
        None,
        "No capability is needed.",
        "Hello.",
        (),
    )
    task = Task(
        task_id="task-1",
        trace_id="trace-1",
        source_event=event,
        state=TaskState.REASONING,
        task_local_state={"current_decision": decision.to_dict()},
    )
    store = TaskStore(tmp_path)

    store.save(task)
    restored = store.load(task.task_id)

    assert restored is not None
    assert ExecutionDecision.from_dict(
        restored.task.task_local_state["current_decision"]
    ) == decision


def test_task_runtime_executes_unified_complete_decision() -> None:
    event = StandardizedEvent(
        trace_id="trace-runtime",
        source="test",
        payload={"text": "hello"},
        event_type="USER_UTTERANCE",
    )
    handoff = HandoffRequest(
        task_goal="Reply naturally.",
        trigger_event=event,
        user_preference_summary="",
        environment_summary="",
        context_summary="",
        constraints=(),
        completion_criteria=("A concise answer is produced.",),
    )
    decision = ExecutionDecision(
        COMPLETE,
        None,
        None,
        "The greeting needs no external capability.",
        "Hello!",
        (),
    )

    class StubSubAgent:
        def decide_next_action(self, handoff, context, task):
            return decision

    class StubToolManager:
        def get_tool(self, name):
            return None

    class StubExecutor:
        tool_manager = StubToolManager()

        def execute(self, selected, context, task):
            return CapabilityExecutionResult(selected)

    runtime = TaskRuntime(
        task_factory=TaskFactory(task_id_factory=lambda: "task-runtime"),
        subagent=StubSubAgent(),
        executor=StubExecutor(),
    )

    handle = runtime.submit(handoff)
    assert runtime.step(handle.task_id).task.state is TaskState.REASONING
    result = runtime.step(handle.task_id)

    assert result.task.state is TaskState.SUCCEEDED
    assert result.task.task_local_state["completion_summary"] == "Hello!"
