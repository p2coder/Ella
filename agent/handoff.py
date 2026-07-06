from dataclasses import dataclass
from typing import Any

from events import StandardizedEvent

from .formulation import TaskFormulation


@dataclass(frozen=True, slots=True)
class HandoffRequest:
    task_goal: str
    trigger_event: StandardizedEvent
    user_preference_summary: str
    environment_summary: str
    context_summary: str
    constraints: tuple[str, ...]
    completion_criteria: tuple[str, ...]
    task_formulation_prompt_text: str = ""

    @classmethod
    def from_formulation(
        cls,
        formulation: TaskFormulation,
        trigger_event: StandardizedEvent,
    ) -> "HandoffRequest":
        return cls(
            task_goal=formulation.goal,
            trigger_event=trigger_event,
            user_preference_summary=formulation.user_preference_summary,
            environment_summary=formulation.environment_summary,
            context_summary=formulation.context_summary,
            constraints=formulation.constraints,
            completion_criteria=formulation.completion_criteria,
            task_formulation_prompt_text=formulation.prompt_text,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_goal": self.task_goal,
            "trigger_event": self.trigger_event.to_dict(),
            "user_preference_summary": self.user_preference_summary,
            "environment_summary": self.environment_summary,
            "context_summary": self.context_summary,
            "constraints": self.constraints,
            "completion_criteria": self.completion_criteria,
            "task_formulation_prompt_text": self.task_formulation_prompt_text,
        }
