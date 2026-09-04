from agent.context import AgentExecutionContext, CapabilityScope
from agent.subagent import SubAgent
from providers.base import ProviderResult
from skill.manager import SkillManager
from tasks.task import Task, TaskState

from tests.runtime.test_first_decision_flow import _event


class CapturingProvider:
    provider_name = "repair-test"
    model_name = "test-model"

    def __init__(self) -> None:
        self.prompt = ""

    def generate(self, prompt, *, trace_id=None, metadata=None):
        self.prompt = prompt
        return ProviderResult(
            self.provider_name,
            self.model_name,
            trace_id,
            {
                "intent": {
                    "goal": "Answer the user.",
                    "constraints": [],
                    "deliverables": ["A response."],
                    "minimum_acceptance_criteria": ["The response is relevant."],
                },
                "action": {
                    "action": "SUBMIT_RESULT",
                    "tool_name": None,
                    "tool_input": None,
                    "decision_reason": "No Tool is required.",
                    "completion_summary": "Answer directly.",
                    "final_response_draft": "Here is a direct answer.",
                    "evidence_refs": [],
                },
            },
        )


def test_first_decision_prompt_contains_exact_action_contract_and_repair() -> None:
    event = _event()
    context = AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-repair",
        trace_id=event.trace_id,
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ()),
    )
    task = Task(
        task_id=context.task_id,
        trace_id=event.trace_id,
        source_event=event,
        execution_context=context,
        state=TaskState.REASONING,
        task_local_state={
            "decision_repair": {
                "validation_error": "decision_reason is required",
                "retry_index": 1,
            }
        },
    )
    provider = CapturingProvider()

    decision = SubAgent(SkillManager(), llm_provider=provider).decide_first_action(
        context, task
    )

    assert decision.action.decision_reason == "No Tool is required."
    assert '"decision_reason":"<non-empty reason>"' in provider.prompt
    assert '"goal":"<one concrete outcome>"' in provider.prompt
    assert "use [] when none apply" in provider.prompt
    assert "never emit blank strings or placeholder entries" in provider.prompt
    assert "not an execution plan" in provider.prompt
    assert "set minimum_acceptance_criteria to []" in provider.prompt
    assert '"final_response_draft":"<complete user-facing answer>"' in provider.prompt
    assert "decision_reason is required" in provider.prompt
    assert "retry_index" in provider.prompt
