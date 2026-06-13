from dataclasses import dataclass
from typing import Any

from events import StandardizedEvent
from providers.llm import LLMProvider


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


@dataclass(frozen=True, slots=True)
class TaskFormulator:
    llm_provider: LLMProvider | None = None

    def formulate(
        self,
        trigger_event: StandardizedEvent,
        user_preference_summary: str,
        environment_summary: str,
        current_agent_input: str | None = None,
    ) -> TaskFormulation:
        text = current_agent_input or str(trigger_event.payload.get("text", ""))
        if self._is_going_out_input(text):
            goal = "Give the user a short, necessary reminder before leaving."
            context_summary = "User said they are about to leave."
            completion_criteria = (
                "A concise pre-leaving reminder goal is ready for handoff.",
            )
        else:
            goal = "Clarify and prepare a concise response to the user input."
            context_summary = "User provided an allowed event for task entry."
            completion_criteria = (
                "A clear task goal is ready for handoff.",
            )

        deterministic = TaskFormulation(
            goal=goal,
            constraints=(
                "Keep the reminder short and necessary.",
                "Use only the provided input, preference summary, and environment summary.",
                "Do not choose a skill or execution strategy.",
            ),
            context_summary=context_summary,
            user_preference_summary=user_preference_summary,
            environment_summary=environment_summary,
            completion_criteria=completion_criteria,
        )

        if self.llm_provider is None:
            return deterministic

        try:
            provider_result = self.llm_provider.generate(
                self._build_prompt(
                    text=text,
                    user_preference_summary=user_preference_summary,
                    environment_summary=environment_summary,
                ),
                trace_id=trigger_event.trace_id,
                metadata={"boundary": "task_formulation"},
            )
        except Exception as error:
            return self._fallback(
                deterministic,
                provider_name=self.llm_provider.provider_name,
                code="provider_exception",
                message=str(error),
            )

        if provider_result.failed:
            return self._fallback(
                deterministic,
                provider_name=provider_result.error.provider_name,
                code=provider_result.error.code,
                message=provider_result.error.message,
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
        )

    def _is_going_out_input(self, text: str) -> bool:
        normalized = text.lower()
        return "出门" in normalized or "heading out" in normalized or "leaving" in normalized

    def _build_prompt(
        self,
        *,
        text: str,
        user_preference_summary: str,
        environment_summary: str,
    ) -> str:
        return (
            "Formulate only what should be done. "
            f"Input: {text}\n"
            f"User preferences: {user_preference_summary}\n"
            f"Environment: {environment_summary}"
        )

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
    ) -> TaskFormulation:
        return TaskFormulation(
            goal=deterministic.goal,
            constraints=deterministic.constraints,
            context_summary=deterministic.context_summary,
            user_preference_summary=deterministic.user_preference_summary,
            environment_summary=deterministic.environment_summary,
            completion_criteria=deterministic.completion_criteria,
            formulation_source="deterministic_fallback",
            provider_error={
                "provider_name": provider_name,
                "code": code,
                "message": message,
            },
        )
