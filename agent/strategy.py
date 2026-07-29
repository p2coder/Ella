from dataclasses import dataclass


@dataclass(frozen=True, slots=True, init=False)
class StrategyDecision:
    mode: str
    skill_name: str | None
    reason: str
    initial_plan: tuple[str, ...] | None
    completion_criteria: tuple[str, ...]
    task_id: str | None = None
    trace_id: str | None = None

    def __init__(
        self,
        mode: str,
        skill_name: str | None,
        reason: str,
        initial_plan: tuple[str, ...] | None,
        completion_criteria: tuple[str, ...],
        task_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "skill_name", skill_name)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "initial_plan", initial_plan)
        object.__setattr__(self, "completion_criteria", completion_criteria)
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "trace_id", trace_id)
