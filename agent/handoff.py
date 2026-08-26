from dataclasses import dataclass
from typing import Any

from events import StandardizedEvent

@dataclass(frozen=True, slots=True)
class HandoffRequest:
    task_goal: str
    trigger_event: StandardizedEvent
    user_preference_summary: str
    environment_summary: str
    context_summary: str
    constraints: tuple[str, ...]
    completion_criteria: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_goal": self.task_goal,
            "trigger_event": self.trigger_event.to_dict(),
            "user_preference_summary": self.user_preference_summary,
            "environment_summary": self.environment_summary,
            "context_summary": self.context_summary,
            "constraints": self.constraints,
            "completion_criteria": self.completion_criteria,
        }
