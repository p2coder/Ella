from datetime import datetime, timezone

from agent.context import AgentExecutionContext, CapabilityScope
from agent.subagent import SubAgent
from events import StandardizedEvent
from providers.base import ProviderResult
from runtime.task_runtime import TaskRuntime
from skill.manager import SkillManager
from tasks.factory import TaskFactory
from tasks.task import Task, TaskState


class FirstDecisionProvider:
    provider_name = "first-decision-test"
    model_name = "test-model"

    def generate(self, prompt, *, trace_id=None, metadata=None):
        assert metadata == {"boundary": "first_decision"}
        return ProviderResult(
            self.provider_name,
            self.model_name,
            trace_id,
            {
                "intent": {
                    "goal": "Greet the user naturally.",
                    "constraints": ["Be concise."],
                    "deliverables": ["A greeting."],
                    "minimum_acceptance_criteria": [
                        "The response acknowledges the greeting."
                    ],
                },
                "action": {
                    "action": "COMPLETE",
                    "decision_reason": "No external capability is needed.",
                    "completion_summary": "Reply with a greeting.",
                    "evidence_refs": [],
                },
            },
        )


def _event() -> StandardizedEvent:
    return StandardizedEvent(
        trace_id="trace-first-decision",
        source="test",
        payload={"text": "你好"},
        event_type="USER_UTTERANCE",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        metadata={},
    )


def test_raw_task_is_submitted_without_a_goal() -> None:
    runtime = TaskRuntime(
        task_factory=TaskFactory(task_id_factory=lambda: "task-first-decision")
    )

    handle = runtime.create_task(_event())
    task = runtime.get_task(handle.task_id)

    assert task.state is TaskState.READY
    assert task.intent is None
    assert task.handoff is None
    assert task.execution_context.handoff_goal == ""


def test_first_decision_commits_intent_and_pending_action() -> None:
    event = _event()
    context = AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-first-decision",
        trace_id=event.trace_id,
        handoff_goal="",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ()),
    )
    task = Task(
        task_id=context.task_id,
        trace_id=event.trace_id,
        source_event=event,
        execution_context=context,
        state=TaskState.REASONING,
    )
    subagent = SubAgent(
        skill_manager=SkillManager(),
        llm_provider=FirstDecisionProvider(),
    )

    result = subagent.decide_first_action(context, task)

    assert result.intent is not None
    assert result.intent.goal == "Greet the user naturally."
    assert result.action.action == "COMPLETE"
    assert "minimum_acceptance_criteria" in task.task_local_state[
        "first_decision_prompt_text"
    ]
