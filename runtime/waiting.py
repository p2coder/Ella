from datetime import datetime, timezone

from tasks.state import (
    StepToolAvailability,
    StepToolAvailabilityState,
)


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
