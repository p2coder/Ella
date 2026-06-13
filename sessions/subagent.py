from dataclasses import dataclass

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from skill.registry import SkillRegistry

from .session import TaskSession
from .strategy import StrategyDecision


@dataclass(frozen=True, slots=True)
class SubAgent:
    skill_registry: SkillRegistry

    def select_strategy(
        self,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
        task_session: TaskSession,
    ) -> StrategyDecision:
        if self._can_use_going_out_skill(handoff):
            return StrategyDecision(
                mode="skill",
                skill_name="going_out",
                reason="Task goal matches the going-out reminder skill metadata.",
                initial_plan=None,
                completion_criteria=handoff.completion_criteria,
                session_id=context.session_id,
                task_id=context.task_id,
                trace_id=context.trace_id,
            )

        return StrategyDecision(
            mode="plan_to_execute",
            skill_name=None,
            reason="No registered skill summary clearly matches the task goal.",
            initial_plan=("Clarify the task before execution.",),
            completion_criteria=handoff.completion_criteria,
            session_id=task_session.session_id,
            task_id=task_session.task_id,
            trace_id=context.trace_id,
        )

    def _can_use_going_out_skill(self, handoff: HandoffRequest) -> bool:
        skill = self.skill_registry.get("going_out")
        if skill is None:
            return False

        goal = handoff.task_goal.lower()
        summary_text = f"{skill.description} {skill.when_to_use}".lower()
        return (
            ("leaving" in goal or "before leaving" in goal)
            and ("leaving" in summary_text or "heading out" in summary_text)
        )
