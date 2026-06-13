from dataclasses import dataclass

from events import StandardizedEvent


@dataclass(frozen=True, slots=True)
class TaskFormulation:
    goal: str
    constraints: tuple[str, ...]
    context_summary: str
    user_preference_summary: str
    environment_summary: str
    completion_criteria: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TaskFormulator:
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

        return TaskFormulation(
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

    def _is_going_out_input(self, text: str) -> bool:
        normalized = text.lower()
        return "出门" in normalized or "heading out" in normalized or "leaving" in normalized
