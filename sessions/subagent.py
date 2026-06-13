from dataclasses import dataclass

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from skill.manager import SkillManager

from .decision import CALL_TOOL, COMPLETE, REPLAN, ExecutionDecision
from .session import TaskSession
from .strategy import StrategyDecision


GOING_OUT_TOOL_SEQUENCE = (
    "mock_vision_summary",
    "mock_weather",
    "mock_checklist",
)

GOING_OUT_VISUAL_TOOL_SEQUENCE = (
    "camera_scene",
    "mock_weather",
    "mock_checklist",
)

VISUAL_REQUEST_MARKERS = (
    "camera",
    "current view",
    "current scene",
    "visual context",
    "look at",
    "see whether",
    "画面",
    "看看",
    "看到",
    "视觉",
    "摄像头",
)


@dataclass(frozen=True, slots=True)
class SubAgent:
    skill_manager: SkillManager

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

    def replan_if_unavailable(
        self,
        decision: StrategyDecision,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
        task_session: TaskSession,
    ) -> StrategyDecision:
        if (
            decision.skill_name is not None
            and self.skill_manager.get_summary(decision.skill_name) is None
        ):
            return self.select_strategy(handoff, context, task_session)
        return decision

    def decide_next_action(
        self,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
        task_session: TaskSession,
        strategy: StrategyDecision,
    ) -> ExecutionDecision:
        if (
            strategy.skill_name != "going_out"
            or self.skill_manager.get_summary("going_out") is None
        ):
            return ExecutionDecision(
                action=REPLAN,
                tool_name=None,
                tool_input=None,
                reason="The current strategy has no available single-step action.",
                is_complete=False,
            )

        completed_tools = {
            entry.get("tool_name")
            for entry in task_session.tool_trace
            if isinstance(entry, dict)
        }
        tool_sequence = self._going_out_tool_sequence(handoff, context)
        for tool_name in tool_sequence:
            if tool_name not in completed_tools:
                return ExecutionDecision(
                    action=CALL_TOOL,
                    tool_name=tool_name,
                    tool_input={
                        "task_goal": handoff.task_goal,
                        "session_id": context.session_id,
                    },
                    reason=f"Collect the next required going-out input with {tool_name}.",
                    is_complete=False,
                )

        return ExecutionDecision(
            action=COMPLETE,
            tool_name=None,
            tool_input=None,
            reason="All required going-out tool results are present.",
            is_complete=True,
        )

    def _going_out_tool_sequence(
        self,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
    ) -> tuple[str, ...]:
        if (
            "camera_scene" in context.allowed_tools
            and self._needs_visual_context(handoff)
        ):
            return GOING_OUT_VISUAL_TOOL_SEQUENCE
        return GOING_OUT_TOOL_SEQUENCE

    def _needs_visual_context(self, handoff: HandoffRequest) -> bool:
        request_text = " ".join(
            (
                handoff.task_goal,
                handoff.context_summary,
                handoff.environment_summary,
                str(handoff.trigger_event.payload.get("text", "")),
            )
        ).lower()
        return any(marker in request_text for marker in VISUAL_REQUEST_MARKERS)

    def _can_use_going_out_skill(self, handoff: HandoffRequest) -> bool:
        skill = self.skill_manager.get_summary("going_out")
        if skill is None:
            return False

        goal = handoff.task_goal.lower()
        summary_text = f"{skill.description} {skill.when_to_use}".lower()
        return (
            ("leaving" in goal or "before leaving" in goal)
            and ("leaving" in summary_text or "heading out" in summary_text)
        )
