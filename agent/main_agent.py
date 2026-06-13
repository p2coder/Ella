from dataclasses import dataclass

from events import StandardizedEvent

from .formulation import TaskFormulator
from .handoff import HandoffRequest


@dataclass(frozen=True, slots=True)
class MainAgent:
    formulator: TaskFormulator = TaskFormulator()

    def create_handoff(
        self,
        trigger_event: StandardizedEvent,
        user_preference_summary: str,
        environment_summary: str,
        current_agent_input: str | None = None,
    ) -> HandoffRequest:
        formulation = self.formulator.formulate(
            trigger_event=trigger_event,
            user_preference_summary=user_preference_summary,
            environment_summary=environment_summary,
            current_agent_input=current_agent_input,
        )
        return HandoffRequest.from_formulation(
            formulation=formulation,
            trigger_event=trigger_event,
        )
