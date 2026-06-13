from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    mode: str
    skill_name: str | None
    reason: str
    initial_plan: tuple[str, ...] | None
    completion_criteria: tuple[str, ...]
    session_id: str | None = None
    task_id: str | None = None
    trace_id: str | None = None
