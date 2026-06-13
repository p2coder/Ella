from dataclasses import dataclass

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from skill import SkillManager
from tools import CapabilityUnavailableError, ToolManager, ToolResult

from .decision import CALL_TOOL, REPLAN, ExecutionDecision
from .session import TaskSession
from .strategy import StrategyDecision
from .subagent import SubAgent


@dataclass(frozen=True, slots=True)
class CapabilityExecutionResult:
    decision: ExecutionDecision
    strategy: StrategyDecision
    tool_result: ToolResult | None
    replan_required: bool
    failure_reason: str | None = None
    unavailable_tool: str | None = None

    @property
    def tool_results(self) -> tuple[ToolResult, ...]:
        if self.tool_result is None:
            return ()
        return (self.tool_result,)

    @property
    def unavailable_tools(self) -> tuple[str, ...]:
        if self.unavailable_tool is None:
            return ()
        return (self.unavailable_tool,)

    @property
    def replanned(self) -> bool:
        return self.replan_required


@dataclass(frozen=True, slots=True)
class CapabilityExecutor:
    skill_manager: SkillManager
    tool_manager: ToolManager
    subagent: SubAgent | None = None

    def execute(
        self,
        decision: ExecutionDecision | StrategyDecision | None = None,
        strategy: StrategyDecision | HandoffRequest | None = None,
        context: AgentExecutionContext | None = None,
        task_session: TaskSession | None = None,
        handoff: HandoffRequest | None = None,
    ) -> CapabilityExecutionResult:
        decision, strategy = self._normalize_request(
            decision=decision,
            strategy=strategy,
            context=context,
            task_session=task_session,
            handoff=handoff,
        )
        if context is None or task_session is None:
            raise TypeError("context and task_session are required")

        if (
            strategy.skill_name is not None
            and self.skill_manager.get_summary(strategy.skill_name) is None
        ):
            return self._failure(
                decision=decision,
                strategy=strategy,
                reason=f"skill {strategy.skill_name} is not registered",
            )

        if decision.action == REPLAN:
            return CapabilityExecutionResult(
                decision=decision,
                strategy=strategy,
                tool_result=None,
                replan_required=True,
            )

        if decision.action != CALL_TOOL:
            return CapabilityExecutionResult(
                decision=decision,
                strategy=strategy,
                tool_result=None,
                replan_required=False,
            )

        tool_name = decision.tool_name
        if tool_name is None:
            raise ValueError("CALL_TOOL execution decision requires tool_name")
        if tool_name not in context.allowed_tools:
            return self._failure(
                decision=decision,
                strategy=strategy,
                reason=f"tool {tool_name} is not allowed",
                unavailable_tool=tool_name,
            )

        try:
            tool_result = self.tool_manager.execute(tool_name, context)
        except CapabilityUnavailableError as error:
            return self._failure(
                decision=decision,
                strategy=strategy,
                reason=str(error),
                unavailable_tool=tool_name,
            )

        return CapabilityExecutionResult(
            decision=decision,
            strategy=strategy,
            tool_result=tool_result,
            replan_required=False,
        )

    def _normalize_request(
        self,
        decision: ExecutionDecision | StrategyDecision | None,
        strategy: StrategyDecision | HandoffRequest | None,
        context: AgentExecutionContext | None,
        task_session: TaskSession | None,
        handoff: HandoffRequest | None,
    ) -> tuple[ExecutionDecision, StrategyDecision]:
        if isinstance(decision, ExecutionDecision):
            if not isinstance(strategy, StrategyDecision):
                raise TypeError("strategy must be a StrategyDecision")
            return decision, strategy

        legacy_strategy: StrategyDecision | None = None
        legacy_handoff = handoff
        if isinstance(decision, StrategyDecision):
            legacy_strategy = decision
            if isinstance(strategy, HandoffRequest):
                legacy_handoff = strategy
        elif decision is None and isinstance(strategy, StrategyDecision):
            legacy_strategy = strategy

        if legacy_strategy is None:
            raise TypeError("decision must be an ExecutionDecision")
        if context is None or task_session is None or legacy_handoff is None:
            raise TypeError("legacy execution requires handoff, context, and task_session")

        if (
            legacy_strategy.skill_name is not None
            and self.skill_manager.get_summary(legacy_strategy.skill_name) is None
            and self.subagent is not None
        ):
            replanned_strategy = self.subagent.replan_if_unavailable(
                legacy_strategy,
                legacy_handoff,
                context,
                task_session,
            )
            return (
                ExecutionDecision(
                    action=REPLAN,
                    tool_name=None,
                    tool_input=None,
                    reason="The selected skill is no longer available.",
                    is_complete=False,
                ),
                replanned_strategy,
            )

        if not context.allowed_tools:
            return (
                ExecutionDecision(
                    action=REPLAN,
                    tool_name=None,
                    tool_input=None,
                    reason="No allowed tool is available for legacy execution.",
                    is_complete=False,
                ),
                legacy_strategy,
            )

        tool_name = context.allowed_tools[0]
        return (
            ExecutionDecision(
                action=CALL_TOOL,
                tool_name=tool_name,
                tool_input=None,
                reason="Execute one allowed legacy capability action.",
                is_complete=False,
            ),
            legacy_strategy,
        )

    @staticmethod
    def _failure(
        decision: ExecutionDecision,
        strategy: StrategyDecision,
        reason: str,
        unavailable_tool: str | None = None,
    ) -> CapabilityExecutionResult:
        return CapabilityExecutionResult(
            decision=decision,
            strategy=strategy,
            tool_result=None,
            replan_required=True,
            failure_reason=reason,
            unavailable_tool=unavailable_tool,
        )
