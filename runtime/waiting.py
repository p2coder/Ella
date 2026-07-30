from dataclasses import dataclass, field
from datetime import datetime, timezone

from sessions.execution_state import (
    StepToolAvailability,
    StepToolAvailabilityState,
    WaitingCondition,
    WaitingKind,
)


@dataclass(slots=True)
class WaitingRegistry:
    _conditions: dict[str, WaitingCondition] = field(default_factory=dict)

    def register(self, task_id: str, condition: WaitingCondition) -> None:
        self._conditions[task_id] = condition

    def remove(self, task_id: str) -> None:
        self._conditions.pop(task_id, None)

    def should_wake(
        self,
        task_id: str,
        *,
        correlation_key: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        condition = self._conditions.get(task_id)
        if condition is None:
            return False
        if condition.kind is WaitingKind.TIME:
            return (now or datetime.now(timezone.utc)) >= condition.wake_at
        return correlation_key is not None and correlation_key == condition.correlation_key

    def rebuild(self, tasks) -> None:
        self._conditions = {
            task.task_id: task.waiting_condition
            for task in tasks
            if task.waiting_condition is not None
        }


def current_tool_availability(
    availability: StepToolAvailability,
    *,
    now: datetime | None = None,
) -> StepToolAvailability:
    if (
        availability.state is StepToolAvailabilityState.BLOCKED
        and availability.blocked_until is not None
        and (now or datetime.now(timezone.utc)) >= availability.blocked_until
    ):
        return StepToolAvailability(
            availability.step_id,
            availability.tool_name,
            StepToolAvailabilityState.AVAILABLE,
            updated_at=now or datetime.now(timezone.utc),
        )
    return availability
