import json
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from agent.context import AgentExecutionContext
from agent.decision import CALL_TOOL, SUBMIT_RESULT, ExecutionDecision, FirstDecision
from prompts.engine import PromptEngine, PromptType
from providers.base import ProviderResult
from providers.llm import LLMProvider, serialize_tool_definitions
from runtime.timing import NoOpRuntimeTimingRecorder, RuntimeTimingRecorder
from runtime.provider_usage import record_provider_usage
from runtime.context_window import prepare_context
from runtime.trace import NoOpTraceRecorder, TraceRecorder
from skill.manager import SkillManager
from tasks.task import Task, TaskIntent
from tools.manager import ToolManager


class DecisionValidationError(ValueError):
    """A model response could not be normalized into a safe action."""


@dataclass(frozen=True, slots=True)
class SubAgent:
    """Produce exactly one action from the current task/step snapshot."""

    skill_manager: SkillManager
    tool_directory: ToolManager | None = None
    llm_provider: LLMProvider | None = None
    prompt_engine: PromptEngine = field(default_factory=PromptEngine)
    timing_recorder: RuntimeTimingRecorder | NoOpRuntimeTimingRecorder = field(
        default_factory=NoOpRuntimeTimingRecorder
    )
    trace_recorder: TraceRecorder | NoOpTraceRecorder = field(
        default_factory=NoOpTraceRecorder
    )
    context_window_tokens: int = 1_000_000
    context_compression_threshold: float = 0.8

    def decide_first_action(
        self,
        context: AgentExecutionContext,
        task: Task,
    ) -> FirstDecision:
        definitions = self._visible_definitions(context, task)
        serialized = serialize_tool_definitions(definitions)
        user_input = str(
            task.task_local_state.get(
                "latest_user_input",
                "" if task.source_event is None else task.source_event.payload.get("text", ""),
            )
        )
        prompt = self.prompt_engine.build(
            PromptType.FIRST_DECISION,
            {
                "user_prompt": user_input,
                "workspace": {
                    "task_id": task.task_id,
                    "trace_id": context.trace_id,
                    "visible_skills": self._visible_skills(context),
                    "visible_tools": serialized,
                    "observations": self._observations(task),
                    "decision_repair": task.task_local_state.get(
                        "decision_repair"
                    ),
                    "inherited_context": task.task_local_state.get(
                        "inherited_context"
                    ),
                },
            },
        )
        prompt_text = self._prepare_prompt(task, "first_decision", prompt.prompt)
        task.task_local_state["first_decision_prompt_text"] = prompt_text
        if self.llm_provider is None:
            return self._first_decision_fallback(user_input, task, definitions)
        started = perf_counter()
        try:
            result = self.llm_provider.generate(
                prompt_text,
                trace_id=context.trace_id,
                metadata={"boundary": "first_decision"},
            )
        except Exception:
            self._record_boundary_timing(
                context, "first_decision", started, False, None
            )
            record_provider_usage(
                task.task_local_state,
                boundary="first_decision",
                provider=self.llm_provider,
                result=None,
                success=False,
            )
            raise
        self._record_boundary_timing(
            context,
            "first_decision",
            started,
            not result.failed,
            result,
        )
        record_provider_usage(
            task.task_local_state,
            boundary="first_decision",
            provider=self.llm_provider,
            result=result,
            success=not result.failed,
        )
        if result.failed:
            raise DecisionValidationError("first decision provider failed")
        try:
            payload = self._extract_payload(result.output)
            return self._first_decision_from_payload(payload, serialized, ())
        except DecisionValidationError:
            if bool(result.metadata.get("mock")):
                return self._first_decision_fallback(user_input, task, definitions)
            raise

    def _record_boundary_timing(
        self,
        context: AgentExecutionContext,
        boundary: str,
        started: float,
        success: bool,
        result: ProviderResult | None,
    ) -> None:
        provider = result if result is not None else self.llm_provider
        self.timing_recorder.record_llm_call(
            context.trace_id,
            boundary=boundary,
            duration_ms=round((perf_counter() - started) * 1000, 3),
            success=success,
            provider_name=None if provider is None else provider.provider_name,
            model_name=None if provider is None else provider.model_name,
        )

    def decide_next_action(
        self,
        context: AgentExecutionContext,
        task: Task,
        *,
        current_goal: str | None = None,
        completion_criteria: tuple[str, ...] | None = None,
    ) -> ExecutionDecision:
        definitions = self._visible_definitions(context, task)
        serialized = serialize_tool_definitions(definitions)
        observations = self._observations(task)
        overall_goal = task.intent.goal if task.intent is not None else ""
        inherited_criteria = (
            task.intent.minimum_acceptance_criteria
            if task.intent is not None
            else ()
        )
        prompt = self.prompt_engine.build(
            PromptType.EXECUTION_DECISION,
            {
                "user_prompt": task.task_local_state.get(
                    "latest_user_input",
                    "",
                ),
                "workspace": {
                    "task_id": task.task_id,
                    "trace_id": context.trace_id,
                    "overall_goal": overall_goal,
                    "current_goal": current_goal or overall_goal,
                    "completion_criteria": tuple(
                        completion_criteria or inherited_criteria
                    ),
                    "task_state": task.state.value,
                    "visible_skills": self._visible_skills(context),
                    "visible_tools": serialized,
                    "observations": observations,
                    "current_step": self._step_context(task),
                    "decision_repair": task.task_local_state.get(
                        "decision_repair"
                    ),
                    "inherited_context": task.task_local_state.get(
                        "inherited_context"
                    ),
                },
            },
        )
        prompt_text = self._prepare_prompt(
            task, "execution_decision", prompt.prompt
        )
        task.task_local_state["execution_decision_prompt_text"] = prompt_text
        self.trace_recorder.record(
            task_id=task.task_id,
            trace_id=context.trace_id,
            boundary="reasoning.execution_decision",
            event_type="prompt_built",
            payload={
                "prompt_name": prompt.prompt_name,
                "visible_capabilities": tuple(
                    item.get("name") for item in serialized
                ),
                "observation_refs": tuple(item["observation_id"] for item in observations),
            },
        )
        if self.llm_provider is None:
            return self._fallback(task, definitions)

        started = perf_counter()
        try:
            result = self.llm_provider.generate(
                prompt_text,
                trace_id=context.trace_id,
                metadata={"boundary": "execution_decision"},
            )
        except Exception:
            self._record_llm_timing(context, started, False, None)
            record_provider_usage(
                task.task_local_state,
                boundary="execution_decision",
                provider=self.llm_provider,
                result=None,
                success=False,
            )
            raise
        self._record_llm_timing(
            context,
            started,
            not result.failed,
            result,
        )
        record_provider_usage(
            task.task_local_state,
            boundary="execution_decision",
            provider=self.llm_provider,
            result=result,
            success=not result.failed,
        )
        if result.failed:
            raise DecisionValidationError("execution decision provider failed")
        try:
            payload = self._extract_payload(result.output)
            return self._decision_from_payload(payload, serialized, observations)
        except DecisionValidationError:
            if bool(result.metadata.get("mock")):
                return self._fallback(task, definitions)
            raise

    def _record_llm_timing(
        self,
        context: AgentExecutionContext,
        started: float,
        success: bool,
        result: ProviderResult | None,
    ) -> None:
        self._record_boundary_timing(
            context, "execution_decision", started, success, result
        )

    def _prepare_prompt(self, task: Task, boundary: str, text: str) -> str:
        prepared = prepare_context(
            text,
            context_window_tokens=self.context_window_tokens,
            compression_threshold=self.context_compression_threshold,
        )
        if prepared.compression_requested:
            events = tuple(
                task.task_local_state.get("context_compression_requested", ())
            )
            task.task_local_state["context_compression_requested"] = (
                *events,
                {
                    "boundary": boundary,
                    "estimated_tokens": prepared.estimated_tokens,
                },
            )
        return prepared.text

    @classmethod
    def _first_decision_from_payload(
        cls,
        payload: dict[str, Any],
        tools: tuple[dict[str, Any], ...],
        observations: tuple[dict[str, Any], ...],
    ) -> FirstDecision:
        raw_intent = payload.get("intent")
        raw_action = payload.get("action")
        if not isinstance(raw_action, dict):
            raise DecisionValidationError("first decision action is required")
        action = cls._decision_from_payload(raw_action, tools, observations)
        if not isinstance(raw_intent, dict):
            raise DecisionValidationError("first decision requires an intent object")
        try:
            intent = TaskIntent(
                goal=str(raw_intent.get("goal", "")),
                constraints=tuple(raw_intent.get("constraints", ())),
                deliverables=tuple(raw_intent.get("deliverables", ())),
                minimum_acceptance_criteria=tuple(
                    raw_intent.get("minimum_acceptance_criteria", ())
                ),
            )
            return FirstDecision(intent, action)
        except (TypeError, ValueError) as error:
            raise DecisionValidationError(f"invalid first decision: {error}") from error

    @classmethod
    def _first_decision_fallback(
        cls,
        user_input: str,
        task: Task,
        definitions: tuple[Any, ...],
    ) -> FirstDecision:
        normalized = user_input.strip()
        if not normalized:
            if not any(item.name == "ask_user_question" for item in definitions):
                raise DecisionValidationError("empty input requires ask_user_question")
            return FirstDecision(
                TaskIntent(
                    goal="Clarify what the user wants Ella to help accomplish.",
                    deliverables=("A clarified user goal.",),
                ),
                ExecutionDecision(
                    CALL_TOOL,
                    "ask_user_question",
                    {
                        "questions": [
                            {
                                "question": "What would you like Ella to help with?",
                                "options": [
                                    {
                                        "text": "Describe the task in your own words",
                                        "recommended": True,
                                    }
                                ],
                            }
                        ]
                    },
                    "The user's purpose is unclear.",
                ),
            )
        intent = TaskIntent(
            goal=normalized,
            deliverables=("A useful response to the user's request.",),
            minimum_acceptance_criteria=(
                "The response addresses the user's stated request honestly.",
            ),
        )
        return FirstDecision(intent, cls._fallback(task, definitions))

    def _visible_definitions(self, context: AgentExecutionContext, task: Task) -> tuple[Any, ...]:
        if self.tool_directory is None:
            return ()
        excluded = set(task.current_step.blacklisted_tools)
        active = task.current_step.active_tool_name
        definitions = tuple(self.tool_directory.list_definitions(context))
        if active is not None:
            return tuple(item for item in definitions if item.name == active)
        return tuple(item for item in definitions if item.name not in excluded)

    def _visible_skills(self, context: AgentExecutionContext) -> tuple[dict[str, object], ...]:
        allowed = set(context.capability_scope.allowed_skills)
        return tuple(
            item
            for item in self.skill_manager.list_summaries_for_role(context.agent_role)
            if not allowed or item.get("name") in allowed
        )

    @staticmethod
    def _observations(task: Task) -> tuple[dict[str, Any], ...]:
        result = []
        for index, item in enumerate(task.tool_trace, start=1):
            observation = dict(item)
            observation.setdefault(
                "observation_id",
                f"{task.task_id}:observation:{index}",
            )
            result.append(observation)
        return tuple(result)

    @staticmethod
    def _step_context(task: Task) -> dict[str, Any]:
        step = task.current_step
        return {
            "attempt_id": step.attempt_id,
            "retry_index": step.retry_index,
            "retries_remaining": step.retries_remaining,
            "active_tool_name": step.active_tool_name,
            "blacklisted_tools": step.blacklisted_tools,
            "failures": tuple(item.to_dict() for item in step.failures),
        }

    @staticmethod
    def _extract_payload(output: Any) -> dict[str, Any]:
        if isinstance(output, dict) and isinstance(output.get("text"), str):
            output = output["text"]
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError as error:
                raise DecisionValidationError("invalid decision JSON") from error
        if not isinstance(output, dict):
            raise DecisionValidationError("decision must be a JSON object")
        return output

    @staticmethod
    def _decision_from_payload(
        payload: dict[str, Any],
        tools: tuple[dict[str, Any], ...],
        observations: tuple[dict[str, Any], ...],
    ) -> ExecutionDecision:
        action = payload.get("action")
        decision_reason = payload.get("decision_reason", payload.get("reason"))
        if not isinstance(decision_reason, str) or not decision_reason.strip():
            decision_reason = f"Model selected {action or 'an unspecified action'}."
        if action == SUBMIT_RESULT:
            summary = payload.get("completion_summary")
            draft = payload.get("final_response_draft")
            refs = payload.get("evidence_refs", ())
            if not isinstance(refs, (list, tuple)):
                raise DecisionValidationError("evidence_refs must be an array")
            known = {item["observation_id"] for item in observations}
            if not set(refs) <= known:
                raise DecisionValidationError("evidence_refs contains an unknown observation")
            return ExecutionDecision(
                SUBMIT_RESULT,
                None,
                None,
                decision_reason,
                summary,
                tuple(refs),
                draft,
            )
        if action != CALL_TOOL:
            raise DecisionValidationError(f"unsupported action: {action}")
        tool_name = payload.get("tool_name")
        visible = {item.get("name") for item in tools}
        if not isinstance(tool_name, str) or tool_name not in visible:
            raise DecisionValidationError("CALL_TOOL requires a visible tool_name")
        arguments = payload.get("arguments", payload.get("tool_input", {}))
        if not isinstance(arguments, dict):
            raise DecisionValidationError("CALL_TOOL arguments must be an object")
        if tool_name == "ask_user_question":
            _reject_repeated_answered_questions(arguments, observations)
        return ExecutionDecision(CALL_TOOL, tool_name, arguments, decision_reason)

    @staticmethod
    def _fallback(task: Task, definitions: tuple[Any, ...]) -> ExecutionDecision:
        if task.tool_trace:
            refs = tuple(
                f"{task.task_id}:observation:{index}"
                for index in range(1, len(task.tool_trace) + 1)
            )
            return ExecutionDecision(
                SUBMIT_RESULT,
                None,
                None,
                "Available observations support a final response.",
                "Use the available observations to answer the user honestly.",
                refs,
                "I completed the request as far as the available observations allow.",
            )
        return ExecutionDecision(
            SUBMIT_RESULT,
            None,
            None,
            "The request can be answered without a capability call.",
            "Respond directly to the user's request.",
            (),
            "I can answer this request directly without an external capability.",
        )


def _reject_repeated_answered_questions(
    arguments: dict[str, Any],
    observations: tuple[dict[str, Any], ...],
) -> None:
    answered: dict[str, set[str]] = {}
    for observation in observations:
        payload = observation.get("payload")
        if not isinstance(payload, dict):
            continue
        for item in payload.get("answers", ()):
            if not isinstance(item, dict) or not str(item.get("answer", "")).strip():
                continue
            question = _normalized_question(item.get("question"))
            if not question:
                continue
            metadata = item.get("metadata")
            phase = (
                str(metadata.get("phase", "")).strip()
                if isinstance(metadata, dict)
                else ""
            )
            answered.setdefault(question, set()).add(phase)

    for item in arguments.get("questions", ()):
        if not isinstance(item, dict):
            continue
        question = _normalized_question(item.get("question"))
        if question not in answered:
            continue
        metadata = item.get("metadata")
        phase = (
            str(metadata.get("phase", "")).strip()
            if isinstance(metadata, dict)
            else ""
        )
        if not phase or phase in answered[question]:
            raise DecisionValidationError(
                "ask_user_question repeated an already answered question in the "
                "same phase; use the accepted user answer from observations"
            )


def _normalized_question(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())
