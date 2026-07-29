from agent.handoff import HandoffRequest
from events import StandardizedEvent
from providers.base import ProviderResult
from sessions.session_manager import TaskFactory
from sessions.subagent import SubAgent
from skill.manager import SkillManager


class LLM:
    provider_name = "test"
    model_name = "test"

    def __init__(self, output):
        self.output = output

    def generate(self, *args, **kwargs):
        return ProviderResult("test", "test", kwargs["trace_id"], self.output)


def creation(output):
    event = StandardizedEvent(
        "trace-plan", "test", {"text": "complex"}, "USER_UTTERANCE", metadata={}
    )
    handoff = HandoffRequest("complex task", event, "", "", "", (), ("done",))
    made = TaskFactory(task_id_factory=lambda: "task-plan").create_task(handoff)
    agent = SubAgent(SkillManager(), llm_provider=LLM(output))
    return agent, made, handoff


def test_plan_requires_estimate_above_five():
    agent, made, handoff = creation(
        {
            "mode": "plan_and_execute",
            "estimated_logical_steps": 6,
            "reason": "complex",
        }
    )
    decision = agent.select_strategy(handoff, made.context, made.task)
    assert decision.mode == "plan"
    assert made.task.task_local_state["estimated_logical_steps"] == 6


def test_missing_or_small_estimate_falls_back_to_react():
    agent, made, handoff = creation(
        {"mode": "plan_and_execute", "estimated_logical_steps": 5}
    )
    assert agent.select_strategy(handoff, made.context, made.task).mode == "react"
