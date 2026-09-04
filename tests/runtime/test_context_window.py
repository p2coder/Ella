import pytest

from runtime.context_window import (
    ContextTooLargeError,
    estimate_tokens,
    prepare_context,
)
from agent.context import AgentExecutionContext, CapabilityScope
from agent.subagent import SubAgent
from skill import SkillManager
from tasks.task import Task, TaskState


def test_estimate_tokens_uses_prd_character_weights_and_ceiling() -> None:
    assert estimate_tokens("abc") == 1
    assert estimate_tokens("中文") == 2
    assert estimate_tokens("é") == 1
    assert estimate_tokens("a中é") == 2


def test_prepare_context_calls_compression_hook_at_threshold() -> None:
    calls = []

    prepared = prepare_context(
        "a" * 8,
        context_window_tokens=3,
        compression_threshold=0.8,
        compressor=lambda text: calls.append(text) or text,
    )

    assert calls == ["a" * 8]
    assert prepared.compression_requested is True
    assert prepared.estimated_tokens == 3


@pytest.mark.parametrize("threshold", (0, 1, -0.1, 1.1))
def test_prepare_context_rejects_invalid_compression_threshold(threshold) -> None:
    with pytest.raises(ValueError, match="compression_threshold"):
        prepare_context("text", compression_threshold=threshold)


def test_noop_compression_rejects_only_after_window_is_exceeded() -> None:
    assert prepare_context(
        "a" * 10,
        context_window_tokens=3,
        compression_threshold=0.8,
    ).estimated_tokens == 3
    with pytest.raises(ContextTooLargeError, match="context_too_large"):
        prepare_context(
            "a" * 11,
            context_window_tokens=3,
            compression_threshold=0.8,
        )


def test_subagent_records_compression_request_on_task() -> None:
    task = Task("task-context", state=TaskState.REASONING)
    task.task_local_state["latest_user_input"] = "abcdefgh"
    context = AgentExecutionContext(
        agent_id="main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id=task.task_id,
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ()),
    )
    agent = SubAgent(
        SkillManager(),
        context_window_tokens=100_000,
        context_compression_threshold=0.0001,
    )

    agent.decide_first_action(context, task)

    event = task.task_local_state["context_compression_requested"][0]
    assert event["boundary"] == "first_decision"
    assert event["estimated_tokens"] > 0
