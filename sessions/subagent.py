import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from prompts.engine import PromptEngine, PromptType
from providers.llm import serialize_tool_definitions
from skill.manager import SkillManager

from .decision import CALL_TOOL, COMPLETE, REPLAN, WAIT, ExecutionDecision
from .session import TaskSession
from .strategy import StrategyDecision


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

MATCH_STOP_WORDS = frozenset(
    {
        "and",
        "for",
        "from",
        "into",
        "the",
        "this",
        "that",
        "use",
        "user",
        "when",
        "with",
    }
)


@dataclass(frozen=True, slots=True)
class SubAgent:
    skill_manager: SkillManager
    tool_directory: Any | None = None
    llm_provider: Any | None = None
    prompt_engine: PromptEngine = field(default_factory=PromptEngine)

    def select_strategy(
        self,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
        task_session: TaskSession,
    ) -> StrategyDecision:
        llm_selection = self._llm_select_strategy_mode(
            handoff,
            context,
        )
        if llm_selection is None:
            mode = "react"
            reason = "Use ReAct as the default execution mode."
            initial_plan = None
        else:
            mode, reason, initial_plan = llm_selection

        return StrategyDecision(
            mode=mode,
            skill_name=None,
            reason=reason,
            initial_plan=initial_plan,
            completion_criteria=handoff.completion_criteria,
            session_id=context.session_id,
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
            and self.skill_manager.get_summary_for_role(
                decision.skill_name,
                context.agent_role,
            )
            is None
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
        print("[subagent]decide_next_action")
        visible_skills = self._visible_skill_summaries(context)
        skill = self._selected_skill(strategy, context)
        if strategy.skill_name is not None and skill is None:
            return self._replan(
                f"Selected skill is no longer available: {strategy.skill_name}"
            )
        if skill is None and strategy.mode == "react":
            skill = self._execution_skill_guidance(
                handoff,
                context,
                visible_skills,
            )

        definitions = self._filter_definitions_for_step(
            self._visible_tool_definitions(context),
            task_session,
        )
        llm_decision = self._llm_decide_next_action(
            handoff,
            context,
            task_session,
            strategy,
            skill,
            definitions,
            visible_skills,
        )
        if llm_decision is not None:
            print("[subagent]llm_desicion is none")
            return llm_decision

        return self._fallback_decision(
            handoff,
            context,
            task_session,
            skill,
            definitions,
        )

    def _visible_skill_summaries(
        self,
        context: AgentExecutionContext,
    ) -> tuple[dict[str, object], ...]:
        allowed_skills = set(context.capability_scope.allowed_skills)
        return tuple(
            summary
            for summary in self.skill_manager.list_summaries_for_role(
                context.agent_role
            )
            if not allowed_skills or summary.get("name") in allowed_skills
        )

    def _selected_skill(
        self,
        strategy: StrategyDecision,
        context: AgentExecutionContext,
    ) -> Any | None:
        if strategy.skill_name is None:
            return None
        allowed_skills = set(context.capability_scope.allowed_skills)
        if allowed_skills and strategy.skill_name not in allowed_skills:
            return None
        return self.skill_manager.get_summary_for_role(
            strategy.skill_name,
            context.agent_role,
        )

    def _execution_skill_guidance(
        self,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
        visible_skills: tuple[dict[str, object], ...],
    ) -> Any | None:
        skill_name = self._metadata_skill_match(handoff, visible_skills)
        if skill_name is None:
            return None
        return self.skill_manager.get_summary_for_role(
            skill_name,
            context.agent_role,
        )

    def _llm_select_strategy_mode(
        self,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
    ) -> tuple[str, str, tuple[str, ...] | None] | None:
        if self.llm_provider is None:
            return None

        prompt = self.prompt_engine.build(
            PromptType.STRATEGY_SELECTION,
            {
                "task": self._task_context(handoff, context),
            },
        )
        result = self.llm_provider.generate(
            prompt.prompt,
            trace_id=context.trace_id,
            metadata={"boundary": "strategy_selection"},
        )
        print("\n[sessions/subagent.py] strategy selected: ",result.output if result else "none")
        if getattr(result, "failed", False):
            return None
        payload = self._extract_decision_payload(result.output)
        if not isinstance(payload, dict):
            return None
        mode = payload.get("mode")
        if mode not in {"react", "plan_and_execute"}:
            return None
        reason = str(payload.get("reason") or "LLM selected execution mode.")
        plan_summary = payload.get("plan_summary")
        initial_plan: tuple[str, ...] | None = None
        if isinstance(plan_summary, str) and plan_summary.strip():
            initial_plan = (plan_summary.strip(),)
        if mode == "plan_and_execute":
            return (
                "react",
                (
                    "LLM requested plan_and_execute, but this runtime only "
                    "supports ReAct execution for now."
                ),
                initial_plan,
            )
        return "react", reason, initial_plan

    def _metadata_skill_match(
        self,
        handoff: HandoffRequest,
        visible_skills: tuple[dict[str, object], ...],
    ) -> str | None:
        task_text = " ".join(
            (
                handoff.task_goal,
                handoff.context_summary,
                handoff.environment_summary,
                str(handoff.trigger_event.payload.get("text", "")),
            )
        ).lower()
        task_tokens = self._meaningful_tokens(task_text)
        best_name: str | None = None
        best_score = 0
        for summary in visible_skills:
            name = summary.get("name")
            if not isinstance(name, str):
                continue
            skill_text = " ".join(
                str(summary.get(key, ""))
                for key in ("name", "description", "when_to_use")
            ).lower()
            skill_tokens = self._meaningful_tokens(skill_text)
            score = len(task_tokens & skill_tokens)
            score += sum(
                1
                for token in skill_tokens
                if len(token) >= 4 and token in task_text
            )
            if score > best_score:
                best_name = name
                best_score = score
        return best_name if best_score > 0 else None

    @staticmethod
    def _meaningful_tokens(text: str) -> set[str]:
        tokens = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", text.lower()))
        return {
            token
            for token in tokens
            if len(token) >= 3 and token not in MATCH_STOP_WORDS
        }

    def _visible_tool_definitions(
        self,
        context: AgentExecutionContext,
    ) -> tuple[Any, ...]:
        if self.tool_directory is None:
            return ()
        return tuple(self.tool_directory.list_definitions(context))

    def _llm_decide_next_action(
        self,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
        task_session: TaskSession,
        strategy: StrategyDecision,
        skill: Any | None,
        definitions: tuple[Any, ...],
        visible_skills: tuple[dict[str, object], ...],
    ) -> ExecutionDecision | None:
        if self.llm_provider is None or self.tool_directory is None:
            return None

        serialized_tools = serialize_tool_definitions(definitions)
        step_context = self._execution_step_context(task_session)
        prompt = self.prompt_engine.build(
            PromptType.EXECUTION_DECISION,
            {
                "user_prompt": handoff.trigger_event.payload.get("text", ""),
                "workspace": {
                    "overall_goal": handoff.task_goal,
                    "current_goal": handoff.task_goal,
                    "current_step_state": {
                        "strategy_mode": strategy.mode,
                        "completion_criteria": strategy.completion_criteria,
                        **step_context,
                    },
                    "task": self._task_context(handoff, context),
                    "selected_skill": self._skill_context(skill),
                    "visible_skills": visible_skills,
                    "visible_tools": serialized_tools,
                    "observations": {
                        "successful_tool_results": step_context[
                            "successful_tool_results"
                        ],
                        "failure_observations": step_context[
                            "failure_observations"
                        ],
                    },
                },
            },
        )
        result = self.llm_provider.generate(
            prompt.prompt,
            trace_id=context.trace_id,
            metadata={"boundary": "execution_decision"},
        )
        print("[subagent]:result: ",result)
        if getattr(result, "failed", False):
            return None
        payload = self._extract_decision_payload(result.output)
        if not isinstance(payload, dict):
            print("[subagent] replan")
            return self._replan("Invalid LLM action decision JSON.")
        decision = self._decision_from_payload(
            payload,
            serialized_tools,
            repair_active_tool=task_session.current_step.active_tool_name,
        )
        return self._correct_visual_wait_decision(
            decision,
            handoff,
            context,
            task_session,
            serialized_tools,
        )

    def _task_context(
        self,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
    ) -> dict[str, object]:
        return {
            "goal": handoff.task_goal,
            "user_input": handoff.trigger_event.payload.get("text", ""),
            "context_summary": handoff.context_summary,
            "user_preference_summary": handoff.user_preference_summary,
            "environment_summary": handoff.environment_summary,
            "constraints": None,
            "completion_criteria": handoff.completion_criteria,
            "trace_id": context.trace_id,
        }

    def _skill_context(self, skill: Any | None) -> dict[str, object] | None:
        if skill is None:
            return None
        content = getattr(skill, "content", None)
        if content is None:
            try:
                content = self.skill_manager.load_full(skill.name).content
            except (FileNotFoundError, KeyError, ValueError):
                content = None
        return {
            "name": skill.name,
            "description": skill.description,
            "when_to_use": skill.when_to_use,
            "required_tools": tuple(getattr(skill, "required_tools", ()) or ()),
            "optional_tools": tuple(getattr(skill, "optional_tools", ()) or ()),
            "content": content,
        }

    def _execution_step_context(
        self,
        task_session: TaskSession,
    ) -> dict[str, object]:
        step = task_session.current_step
        historical_failures = tuple(
            failure.to_dict()
            for archived_step in task_session.step_history
            for failure in archived_step.failures
        )
        current_failures = tuple(failure.to_dict() for failure in step.failures)
        return {
            "attempt_id": step.attempt_id,
            "retry_index": step.retry_index,
            "active_tool_name": step.active_tool_name,
            "repair_mode": step.active_tool_name is not None,
            "retries_remaining": step.retries_remaining,
            "blacklisted_tools": step.blacklisted_tools,
            "failures": current_failures,
            "successful_tool_results": task_session.tool_trace,
            "failure_observations": (*historical_failures, *current_failures),
        }

    def _filter_definitions_for_step(
        self,
        definitions: tuple[Any, ...],
        task_session: TaskSession,
    ) -> tuple[Any, ...]:
        step = task_session.current_step
        if step.active_tool_name is not None:
            return tuple(
                definition
                for definition in definitions
                if getattr(definition, "name", None) == step.active_tool_name
            )

        excluded = set(step.blacklisted_tools)
        excluded.update(self._non_retryable_failed_tool_names(task_session))
        if self._has_successful_observation(task_session, "camera_scene"):
            excluded.add("camera_scene")
        return tuple(
            definition
            for definition in definitions
            if getattr(definition, "name", None) not in excluded
        )

    def _fallback_decision(
        self,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
        task_session: TaskSession,
        skill: Any | None,
        definitions: tuple[Any, ...],
    ) -> ExecutionDecision:
        if skill is None:
            if task_session.tool_trace:
                return ExecutionDecision(
                    action=COMPLETE,
                    tool_name=None,
                    tool_input=None,
                    reason="Available observations are ready for task completion.",
                    is_complete=True,
                )
            return ExecutionDecision(
                action=COMPLETE,
                tool_name=None,
                tool_input=None,
                reason=(
                    "No skill or tool is required; complete from the user input."
                ),
                is_complete=True,
            )

        visible_names = self._visible_tool_names(context, definitions)
        tool_order = self._skill_guided_tool_order(skill, handoff, visible_names)
        completed_tools = {
            entry.get("tool_name")
            for entry in task_session.tool_trace
            if isinstance(entry, dict)
        }
        failed_tools = self._non_retryable_failed_tool_names(task_session)
        resolved_tools = completed_tools | failed_tools
        unavailable = tuple(
            name
            for name in tool_order
            if name not in visible_names and name not in resolved_tools
        )
        if unavailable:
            return self._replan(
                "Skill-referenced tools are no longer available: "
                + ", ".join(unavailable)
            )

        definitions_by_name = {
            definition.name: definition
            for definition in definitions
            if isinstance(getattr(definition, "name", None), str)
        }
        for tool_name in tool_order:
            if tool_name not in resolved_tools:
                return ExecutionDecision(
                    action=CALL_TOOL,
                    tool_name=tool_name,
                    tool_input=self._fallback_arguments(
                        definitions_by_name.get(tool_name),
                        handoff,
                        context,
                    ),
                    reason=f"Collect the next required input with {tool_name}.",
                    is_complete=False,
                )

        return ExecutionDecision(
            action=COMPLETE,
            tool_name=None,
            tool_input=None,
            reason="The skill-guided observations are ready for completion.",
            is_complete=True,
        )

    def _visible_tool_names(
        self,
        context: AgentExecutionContext,
        definitions: tuple[Any, ...],
    ) -> tuple[str, ...]:
        if self.tool_directory is None:
            return context.allowed_tools
        return tuple(
            definition.name
            for definition in definitions
            if isinstance(getattr(definition, "name", None), str)
        )

    def _skill_guided_tool_order(
        self,
        skill: Any,
        handoff: HandoffRequest,
        visible_names: tuple[str, ...],
    ) -> tuple[str, ...]:
        required_tools = tuple(getattr(skill, "required_tools", ()) or ())
        optional_tools = tuple(getattr(skill, "optional_tools", ()) or ())
        if not required_tools and not optional_tools:
            return self._legacy_visible_tool_order(handoff, visible_names)

        ordered = list(self._selected_optional_tools(optional_tools, handoff))
        ordered.extend(name for name in required_tools if name not in ordered)
        return tuple(ordered)

    def _selected_optional_tools(
        self,
        optional_tools: tuple[str, ...],
        handoff: HandoffRequest,
    ) -> tuple[str, ...]:
        if self._needs_visual_context(handoff):
            visual_tools = tuple(
                name
                for name in optional_tools
                if self._tool_name_suggests_visual_context(name)
            )
            return visual_tools[:1]
        return tuple(
            name
            for name in optional_tools
            if not self._tool_name_suggests_camera_capture(name)
        )

    def _legacy_visible_tool_order(
        self,
        handoff: HandoffRequest,
        visible_names: tuple[str, ...],
    ) -> tuple[str, ...]:
        if not self._needs_visual_context(handoff):
            return tuple(
                name
                for name in visible_names
                if not self._tool_name_suggests_camera_capture(name)
            )
        visual = tuple(
            name
            for name in visible_names
            if self._tool_name_suggests_visual_context(name)
        )
        non_visual = tuple(name for name in visible_names if name not in visual)
        return (*visual[:1], *non_visual)

    @staticmethod
    def _tool_name_suggests_visual_context(tool_name: str) -> bool:
        normalized = tool_name.lower()
        return any(
            marker in normalized
            for marker in ("camera", "vision", "visual", "scene")
        )

    @staticmethod
    def _tool_name_suggests_camera_capture(tool_name: str) -> bool:
        return "camera" in tool_name.lower()

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

    @staticmethod
    def _fallback_arguments(
        definition: Any | None,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
    ) -> dict[str, object]:
        examples = getattr(definition, "input_examples", ()) if definition else ()
        if examples and isinstance(examples[0], dict):
            return dict(examples[0])
        return {
            "task_goal": handoff.task_goal,
            "session_id": context.session_id,
        }

    @staticmethod
    def _extract_decision_payload(output: Any) -> dict[str, Any] | None:
        if isinstance(output, dict) and isinstance(output.get("text"), str):
            return SubAgent._loads_json_object(output["text"])
        if isinstance(output, dict):
            return output
        if isinstance(output, str):
            return SubAgent._loads_json_object(output)
        return None

    @staticmethod
    def _loads_json_object(text: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _decision_from_payload(
        self,
        payload: dict[str, Any],
        serialized_tools: tuple[dict[str, Any], ...],
        repair_active_tool: str | None = None,
    ) -> ExecutionDecision:
        action = payload.get("action")
        reason = str(payload.get("reason") or "LLM selected the next action.")
        if action not in {CALL_TOOL, COMPLETE, WAIT, REPLAN}:
            return self._replan(f"Unsupported LLM action decision: {action}")
        if action == COMPLETE:
            return ExecutionDecision(COMPLETE, None, None, reason, True)
        if action == WAIT:
            return ExecutionDecision(WAIT, None, None, reason, False)
        if action == REPLAN:
            return self._replan(reason)

        tool_name = payload.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name:
            return self._replan("CALL_TOOL decision is missing tool_name.")
        if repair_active_tool is not None and tool_name != repair_active_tool:
            arguments = payload.get("arguments", payload.get("tool_input", {}))
            if not isinstance(arguments, dict):
                arguments = {}
            return ExecutionDecision(CALL_TOOL, tool_name, arguments, reason, False)
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
        missing = self._missing_required_arguments(arguments, visible_by_name[tool_name])
        if missing:
            return self._replan(
                f"Missing required tool arguments for {tool_name}: {', '.join(missing)}"
            )
        return ExecutionDecision(CALL_TOOL, tool_name, arguments, reason, False)

    def _correct_visual_wait_decision(
        self,
        decision: ExecutionDecision,
        handoff: HandoffRequest,
        context: AgentExecutionContext,
        task_session: TaskSession,
        serialized_tools: tuple[dict[str, Any], ...],
    ) -> ExecutionDecision:
        if decision.action != WAIT:
            return decision
        if not self._explicit_screen_request(handoff):
            return decision
        if not self._tool_is_visible("screen_scene", serialized_tools):
            return decision
        if self._has_observation(task_session, "screen_scene"):
            return decision
        return ExecutionDecision(
            CALL_TOOL,
            "screen_scene",
            {
                "max_screenshots": 1,
                "session_id": context.session_id,
                "task_goal": handoff.task_goal,
            },
            (
                "The request explicitly depends on current screen content, "
                "and screen_scene is visible."
            ),
            False,
        )

    @staticmethod
    def _explicit_screen_request(handoff: HandoffRequest) -> bool:
        text = str(handoff.trigger_event.payload.get("text", "")).lower()
        goal = handoff.task_goal.lower()
        combined = f"{text} {goal}"
        return any(
            marker in combined
            for marker in (
                "屏幕",
                "窗口",
                "页面",
                "screen",
                "on my screen",
                "web page",
            )
        )

    @staticmethod
    def _tool_is_visible(
        tool_name: str,
        serialized_tools: tuple[dict[str, Any], ...],
    ) -> bool:
        return any(tool.get("name") == tool_name for tool in serialized_tools)

    @staticmethod
    def _has_observation(task_session: TaskSession, tool_name: str) -> bool:
        for observation in task_session.tool_trace:
            if isinstance(observation, Mapping):
                if observation.get("tool_name") == tool_name:
                    return True
            elif getattr(observation, "tool_name", None) == tool_name:
                return True
        return False

    @staticmethod
    def _has_successful_observation(
        task_session: TaskSession,
        tool_name: str,
    ) -> bool:
        for observation in task_session.tool_trace:
            if isinstance(observation, Mapping):
                observed_name = observation.get("tool_name")
                payload = observation.get("payload", {})
            else:
                observed_name = getattr(observation, "tool_name", None)
                payload = getattr(observation, "payload", {})
            if observed_name != tool_name or not isinstance(payload, Mapping):
                continue
            if payload.get("status") == "unavailable" or payload.get("error"):
                continue
            return True
        return False

    @staticmethod
    def _non_retryable_failed_tool_names(
        task_session: TaskSession,
    ) -> set[str]:
        return {
            failure.tool_name
            for step in (*task_session.step_history, task_session.current_step)
            for failure in step.failures
            if not failure.retryable
        }

    @staticmethod
    def _missing_required_arguments(
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

    @staticmethod
    def _replan(reason: str) -> ExecutionDecision:
        return ExecutionDecision(REPLAN, None, None, reason, False)
