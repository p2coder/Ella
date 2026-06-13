from dataclasses import dataclass

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from skill import SkillManager
from tools import CapabilityUnavailableError, ToolManager, ToolResult

from .session import TaskSession
from .strategy import StrategyDecision
from .subagent import SubAgent


@dataclass(frozen=True, slots=True)
class CapabilityExecutionResult:
    strategy: StrategyDecision
    tool_results: tuple[ToolResult, ...]
    unavailable_tools: tuple[str, ...]
    replanned: bool


@dataclass(frozen=True, slots=True)
class CapabilityExecutor:
    subagent: SubAgent
    skill_manager: SkillManager
    tool_manager: ToolManager

    def execute(
        self,
        strategy: StrategyDecision,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
        task_session: TaskSession,
    ) -> CapabilityExecutionResult:
        current_strategy = self.subagent.replan_if_unavailable(
            strategy,
            handoff,
            context,
            task_session,
        )
        replanned = current_strategy != strategy

        if current_strategy.skill_name is not None:
            self.skill_manager.load_full(current_strategy.skill_name)

        tool_results = []
        unavailable_tools = []
        for tool_name in context.allowed_tools:
            try:
                tool_results.append(self.tool_manager.execute(tool_name, context))
            except CapabilityUnavailableError:
                unavailable_tools.append(tool_name)
                current_strategy = self.subagent.select_strategy(
                    handoff,
                    context,
                    task_session,
                )
                replanned = True

        return CapabilityExecutionResult(
            strategy=current_strategy,
            tool_results=tuple(tool_results),
            unavailable_tools=tuple(unavailable_tools),
            replanned=replanned,
        )
