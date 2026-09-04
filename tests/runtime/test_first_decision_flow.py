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

    def generate(self, prompt, *, task_id=None, metadata=None):
        assert metadata == {"boundary": "first_decision"}
        return ProviderResult(
            self.provider_name,
            self.model_name,
            task_id,
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
                    "action": "SUBMIT_RESULT",
                    "decision_reason": "No external capability is needed.",
                    "completion_summary": "Reply with a greeting.",
                    "final_response_draft": "你好，很高兴见到你。",
                    "evidence_refs": [],
                },
            },
        )


def _event() -> StandardizedEvent:
    return StandardizedEvent(
        task_id="task-first-decision",
        source="test",
        payload={"text": "你好"},
        event_type="USER_UTTERANCE",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        metadata={},
    )


def test_raw_task_is_submitted_without_a_goal() -> None:
    runtime = TaskRuntime(
        task_factory=TaskFactory()
    )

    handle = runtime.create_task(_event())
    task = runtime.get_task(handle.task_id)

    assert task.state is TaskState.READY
    assert task.intent is None


def test_first_decision_commits_intent_and_pending_action() -> None:
    event = _event()
    context = AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-first-decision",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ()),
    )
    task = Task(
        task_id=context.task_id,
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
    assert result.action.action == "SUBMIT_RESULT"
    assert "minimum_acceptance_criteria" in task.task_local_state[
        "first_decision_prompt_text"
    ]
