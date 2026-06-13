from dataclasses import dataclass

from events import StandardizedEvent
from providers.llm import LLMProvider

from .formulation import TaskFormulator
from .handoff import HandoffRequest


@dataclass(frozen=True, slots=True)
class MainAgent:
    formulator: TaskFormulator | None = None
    llm_provider: LLMProvider | None = None

    def __post_init__(self) -> None:
        if self.formulator is None:
            object.__setattr__(
                self,
                "formulator",
                TaskFormulator(llm_provider=self.llm_provider),
            )
        elif self.llm_provider is None:
            object.__setattr__(
                self,
                "llm_provider",
                self.formulator.llm_provider,
            )

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
