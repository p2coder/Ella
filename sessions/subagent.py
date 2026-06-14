import json
from typing import Any
from dataclasses import dataclass

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from providers.llm import serialize_tool_definitions
from skill.manager import SkillManager

from .decision import CALL_TOOL, COMPLETE, REPLAN, WAIT, ExecutionDecision
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
    tool_directory: Any | None = None
    llm_provider: Any | None = None

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

        llm_decision = self._llm_decide_next_action(
            handoff,
            context,
            task_session,
            strategy,
        )
        if llm_decision is not None:
            return llm_decision

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

        task_text = " ".join(
            (
                handoff.task_goal,
                handoff.context_summary,
                str(handoff.trigger_event.payload.get("text", "")),
            )
        ).lower()
        summary_text = f"{skill.description} {skill.when_to_use}".lower()
        return (
            (
                "leaving" in task_text
                or "before leaving" in task_text
                or "heading out" in task_text
                or "出门" in task_text
            )
            and ("leaving" in summary_text or "heading out" in summary_text)
        )

    def _llm_decide_next_action(
        self,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
        task_session: TaskSession,
        strategy: StrategyDecision,
    ) -> ExecutionDecision | None:
        if self.tool_directory is None or self.llm_provider is None:
            return None

        definitions = self.tool_directory.list_definitions(context)
        serialized_tools = serialize_tool_definitions(definitions)
        prompt = json.dumps(
            {
                "instruction": (
                    "Return one JSON object with action CALL_TOOL, COMPLETE, "
                    "WAIT, or REPLAN."
                ),
                "task": {
                    "goal": handoff.task_goal,
                    "context_summary": handoff.context_summary,
                    "user_preference_summary": handoff.user_preference_summary,
                    "environment_summary": handoff.environment_summary,
                    "constraints": handoff.constraints,
                    "completion_criteria": handoff.completion_criteria,
                    "trace_id": context.trace_id,
                    "strategy": {
                        "mode": strategy.mode,
                        "skill_name": strategy.skill_name,
                        "reason": strategy.reason,
                        "initial_plan": strategy.initial_plan,
                        "completion_criteria": strategy.completion_criteria,
                    },
                },
                "tool_results": task_session.tool_trace,
                "visible_tools": serialized_tools,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        result = self.llm_provider.generate(prompt, trace_id=context.trace_id)
        payload = self._extract_decision_payload(result.output)
        if not isinstance(payload, dict):
            return self._replan("Invalid LLM tool decision JSON.")
        return self._decision_from_payload(payload, serialized_tools)

    def _extract_decision_payload(self, output: Any) -> dict[str, Any] | None:
        if isinstance(output, dict) and isinstance(output.get("text"), str):
            return self._loads_json_object(output["text"])
        if isinstance(output, dict):
            return output
        if isinstance(output, str):
            return self._loads_json_object(output)
        return None

    def _loads_json_object(self, text: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _decision_from_payload(
        self,
        payload: dict[str, Any],
        serialized_tools: tuple[dict[str, Any], ...],
    ) -> ExecutionDecision:
        action = payload.get("action")
        reason = str(payload.get("reason") or "LLM selected the next action.")
        if action not in {CALL_TOOL, COMPLETE, WAIT, REPLAN}:
            return self._replan(f"Unsupported LLM tool decision action: {action}")

        if action == COMPLETE:
            return ExecutionDecision(
                action=COMPLETE,
                tool_name=None,
                tool_input=None,
                reason=reason,
                is_complete=True,
            )
        if action == WAIT:
            return ExecutionDecision(
                action=WAIT,
                tool_name=None,
                tool_input=None,
                reason=reason,
                is_complete=False,
            )
        if action == REPLAN:
            return self._replan(reason)

        tool_name = payload.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name:
            return self._replan("CALL_TOOL decision is missing tool_name.")

        visible_by_name = {
            str(tool["name"]): tool
            for tool in serialized_tools
            if isinstance(tool.get("name"), str)
        }
        if tool_name not in visible_by_name:
            return self._replan(f"Unknown tool requested by LLM: {tool_name}")

        arguments = payload.get("arguments", payload.get("tool_input", {}))
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return self._replan("CALL_TOOL arguments must be an object.")

        missing = self._missing_required_arguments(
            arguments,
            visible_by_name[tool_name],
        )
        if missing:
            return self._replan(
                f"Missing required tool arguments for {tool_name}: {', '.join(missing)}"
            )

        return ExecutionDecision(
            action=CALL_TOOL,
            tool_name=tool_name,
            tool_input=arguments,
            reason=reason,
            is_complete=False,
        )

    def _missing_required_arguments(
        self,
        arguments: dict[str, Any],
        serialized_tool: dict[str, Any],
    ) -> tuple[str, ...]:
        input_schema = serialized_tool.get("input_schema")
        if not isinstance(input_schema, dict):
            return ()
        required = input_schema.get("required", ())
        if not isinstance(required, (list, tuple)):
            return ()
        return tuple(
            name
            for name in required
            if isinstance(name, str) and name not in arguments
        )

    def _replan(self, reason: str) -> ExecutionDecision:
        return ExecutionDecision(
            action=REPLAN,
            tool_name=None,
            tool_input=None,
            reason=reason,
            is_complete=False,
        )
