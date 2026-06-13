from dataclasses import dataclass

from events import StandardizedEvent


@dataclass(frozen=True, slots=True)
class InterruptionDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class InterruptionPolicy:
    def evaluate(self, event: StandardizedEvent) -> InterruptionDecision:
        if event.metadata.get("suppress") is True:
            return InterruptionDecision(
                allowed=False,
                reason="event marked as suppressed",
            )

        if event.metadata.get("ambient") is True:
            return InterruptionDecision(
                allowed=False,
                reason="ambient event should not interrupt",
            )

        if event.event_type.endswith("_NOISE"):
            return InterruptionDecision(
                allowed=False,
                reason="event should not interrupt",
            )

        if (
            event.metadata.get("trigger_kind") == "user_initiated"
            or event.event_type == "USER_UTTERANCE"
        ):
            return InterruptionDecision(
                allowed=True,
                reason="user initiated event",
            )

        return InterruptionDecision(
            allowed=False,
            reason="event should not interrupt",
        )
