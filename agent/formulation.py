from dataclasses import dataclass, field
from time import perf_counter
import re
from typing import Any

from events import StandardizedEvent
from prompts.engine import PromptEngine, PromptType
from providers.llm import LLMProvider
from runtime.timing import NoOpRuntimeTimingRecorder, RuntimeTimingRecorder


@dataclass(frozen=True, slots=True)
class TaskFormulation:
    goal: str
    constraints: tuple[str, ...]
    context_summary: str
    user_preference_summary: str
    environment_summary: str
    completion_criteria: tuple[str, ...]
    formulation_source: str = "deterministic"
    provider_error: dict[str, str | None] | None = None
    prompt_text: str = ""


@dataclass(frozen=True, slots=True)
class TaskFormulator:
    llm_provider: LLMProvider | None = None
    prompt_engine: PromptEngine = field(default_factory=PromptEngine)
    timing_recorder: RuntimeTimingRecorder | NoOpRuntimeTimingRecorder = field(
        default_factory=NoOpRuntimeTimingRecorder
    )

    def formulate(
        self,
        trigger_event: StandardizedEvent,
        user_preference_summary: str,
        environment_summary: str,
        current_agent_input: str | None = None,
    ) -> TaskFormulation:
        text = current_agent_input or str(trigger_event.payload.get("text", ""))
        deterministic = self._deterministic_formulation(
            text=text,
            user_preference_summary=user_preference_summary,
            environment_summary=environment_summary,
        )

        if self.llm_provider is None or not self._needs_task_formulation(text):
            return deterministic

        prompt_text = ""
        try:
            prompt_result = self.prompt_engine.build(
                PromptType.TASK_FORMULATION,
                {
                    "user_input": text,
                    "user_preference_summary": user_preference_summary,
                    "environment_summary": environment_summary,
                    "event_type": trigger_event.event_type,
                    "trace_id": trigger_event.trace_id,
                },
            )
            prompt_text = prompt_result.prompt
            llm_started = perf_counter()
            provider_result = self.llm_provider.generate(
                prompt_result.prompt,
                trace_id=trigger_event.trace_id,
                metadata={"boundary": "task_formulation"},
            )
            self.timing_recorder.record_llm_call(
                trigger_event.trace_id,
                boundary="task_formulation",
                duration_ms=round((perf_counter() - llm_started) * 1000, 3),
                success=not provider_result.failed,
                provider_name=provider_result.provider_name,
                model_name=provider_result.model_name,
            )
        except Exception as error:
            if "llm_started" in locals():
                self.timing_recorder.record_llm_call(
                    trigger_event.trace_id,
                    boundary="task_formulation",
                    duration_ms=round(
                        (perf_counter() - llm_started) * 1000,
                        3,
                    ),
                    success=False,
                    provider_name=self.llm_provider.provider_name,
                    model_name=self.llm_provider.model_name,
                )
            return self._fallback(
                deterministic,
                provider_name=self.llm_provider.provider_name,
                code="provider_exception",
                message=str(error),
                prompt_text=prompt_text,
            )

        if provider_result.failed:
            return self._fallback(
                deterministic,
                provider_name=provider_result.error.provider_name,
                code=provider_result.error.code,
                message=provider_result.error.message,
                prompt_text=prompt_result.prompt,
            )

        output = provider_result.output
        provider_goal = self._provider_value(output, "goal")
        if provider_goal is None:
            provider_goal = self._provider_value(output, "text")
        if provider_goal is None:
            return self._fallback(
                deterministic,
                provider_name=provider_result.provider_name,
                code="invalid_provider_output",
                message="provider output did not include a task goal",
                prompt_text=prompt_result.prompt,
            )

        return TaskFormulation(
            goal=provider_goal,
            constraints=deterministic.constraints,
            context_summary=(
                self._provider_value(output, "context_summary")
                or deterministic.context_summary
            ),
            user_preference_summary=user_preference_summary,
            environment_summary=environment_summary,
            completion_criteria=(
                "A provider-generated task goal is ready for handoff.",
            ),
            formulation_source="llm_provider",
            prompt_text=prompt_result.prompt,
        )

    def _deterministic_formulation(
        self,
        *,
        text: str,
        user_preference_summary: str,
        environment_summary: str,
    ) -> TaskFormulation:
        normalized = text.strip()
        if self._is_greeting(normalized):
            goal = "Respond naturally to the user's greeting."
            context_summary = "User sent a greeting."
            completion_criteria = ("A natural greeting response is ready.",)
            constraints = self._default_constraints()
        elif self._looks_ambiguous(normalized):
            goal = "Clarify the user's intent and prepare a useful response."
            context_summary = "User intent may need clarification or formulation."
            completion_criteria = (
                "A clear task goal is ready for handoff.",
            )
            constraints = self._default_constraints()
        elif self._is_going_out_input(normalized):
            goal = "Give the user a short, necessary reminder before leaving."
            context_summary = "User said they are about to leave."
            completion_criteria = (
                "A concise pre-leaving reminder goal is ready for handoff.",
            )
            constraints = (
                "Keep the reminder short and necessary.",
                "Use only the provided input, preference summary, and environment summary.",
                "Do not choose a skill or execution strategy.",
            )
        elif self._is_question(normalized):
            goal = "Answer the user's question directly."
            context_summary = "User asked a question."
            completion_criteria = ("The user's question is answered.",)
            constraints = self._default_constraints()
        elif self._is_clear_direct_instruction(normalized):
            goal = "Complete the user's direct instruction."
            context_summary = "User gave a clear direct instruction."
            completion_criteria = ("The direct instruction is handled.",)
            constraints = self._default_constraints()
        else:
            goal = "Respond usefully to the user's input."
            context_summary = "User provided a general input."
            completion_criteria = ("A useful response is ready.",)
            constraints = self._default_constraints()

        return TaskFormulation(
            goal=goal,
            constraints=constraints,
            context_summary=context_summary,
            user_preference_summary=user_preference_summary,
            environment_summary=environment_summary,
            completion_criteria=completion_criteria,
        )

    @staticmethod
    def _default_constraints() -> tuple[str, ...]:
        return (
            "Use only the provided input, preference summary, and environment summary.",
            "Do not choose a skill or execution strategy.",
            "Do not choose or call tools during task formulation.",
        )

    def _needs_task_formulation(self, text: str) -> bool:
        normalized = text.strip()
        if not normalized:
            return True
        if self._is_greeting(normalized):
            return False
        if self._looks_ambiguous(normalized):
            return True
        if self._is_question(normalized):
            return False
        if self._is_going_out_input(normalized):
            return False
        if self._is_clear_direct_instruction(normalized):
            return False
        return self._looks_ambiguous(normalized)

    def _is_greeting(self, text: str) -> bool:
        normalized = re.sub(r"[\s!！。,.，？?]", "", text.lower())
        return normalized in {
            "你好",
            "您好",
            "嗨",
            "hello",
            "hi",
            "hey",
            "ella你好",
            "helloella",
            "hiella",
        }

    def _is_question(self, text: str) -> bool:
        normalized = text.lower()
        return (
            "?" in normalized
            or "？" in normalized
            or any(
                marker in normalized
                for marker in (
                    "什么",
                    "为什么",
                    "怎么",
                    "如何",
                    "多少",
                    "哪里",
                    "能不能",
                    "可以吗",
                    "what",
                    "why",
                    "how",
                    "where",
                    "when",
                    "can you",
                )
            )
        )

    def _is_clear_direct_instruction(self, text: str) -> bool:
        normalized = text.lower()
        return any(
            marker in normalized
            for marker in (
                "帮我",
                "请",
                "总结",
                "解释",
                "翻译",
                "写",
                "生成",
                "列出",
                "整理",
                "提醒我",
                "please",
                "summarize",
                "explain",
                "translate",
                "write",
                "list",
                "remind me",
            )
        )

    def _looks_ambiguous(self, text: str) -> bool:
        normalized = text.lower()
        return any(
            marker in normalized
            for marker in (
                "有点迷茫",
                "不知道",
                "怎么办",
                "帮帮我",
                "随便",
                "你觉得",
                "不确定",
                "confused",
                "not sure",
                "what should i do",
            )
        )

    def _is_going_out_input(self, text: str) -> bool:
        normalized = text.lower()
        return "出门" in normalized or "heading out" in normalized or "leaving" in normalized

    def _provider_value(self, output: Any, key: str) -> str | None:
        if not isinstance(output, dict):
            return None
        value = output.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()

    def _fallback(
        self,
        deterministic: TaskFormulation,
        *,
        provider_name: str,
        code: str | None,
        message: str,
        prompt_text: str = "",
    ) -> TaskFormulation:
        return TaskFormulation(
            goal=deterministic.goal,
            constraints=deterministic.constraints,
            context_summary=deterministic.context_summary,
            user_preference_summary=deterministic.user_preference_summary,
            environment_summary=deterministic.environment_summary,
            completion_criteria=deterministic.completion_criteria,
            formulation_source="deterministic_fallback",
            prompt_text=prompt_text,
            provider_error={
                "provider_name": provider_name,
                "code": code,
                "message": message,
            },
        )
