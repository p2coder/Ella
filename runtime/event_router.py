from dataclasses import dataclass

from events import StandardizedEvent


@dataclass(frozen=True, slots=True)
class RouteDestination:
    name: str
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("route destination name must not be empty")


SESSION_INBOX = RouteDestination(
    "SESSION_INBOX",
    "Route the event back to an active task session inbox.",
)
AMBIENT_STATE = RouteDestination(
    "AMBIENT_STATE",
    "Update ambient state without entering active presence handling.",
)
SUPPRESSED = RouteDestination(
    "SUPPRESSED",
    "Suppress or record an event without further handling.",
)
PRESENCE_QUEUE = RouteDestination(
    "PRESENCE_QUEUE",
    "Queue the event for later Presence Runtime handling.",
)

DEFAULT_ROUTE_DESTINATIONS = (
    SESSION_INBOX,
    AMBIENT_STATE,
    SUPPRESSED,
    PRESENCE_QUEUE,
)


class RouteDestinationRegistry:
    def __init__(
        self,
        destinations: tuple[RouteDestination, ...] = DEFAULT_ROUTE_DESTINATIONS,
    ) -> None:
        self._destinations: dict[str, RouteDestination] = {}
        for destination in destinations:
            self.register(destination)

    def register(self, destination: RouteDestination) -> None:
        self._destinations[destination.name] = destination

    def unregister(self, destination_name: str) -> None:
        self._destinations.pop(destination_name, None)

    def get(self, destination_name: str) -> RouteDestination | None:
        return self._destinations.get(destination_name)

    def list_destinations(self) -> tuple[RouteDestination, ...]:
        return tuple(self._destinations.values())


@dataclass(frozen=True, slots=True)
class EventRouteResult:
    event: StandardizedEvent
    destination: RouteDestination
    reason: str
    target_session_id: str | None = None


@dataclass(frozen=True, slots=True)
class SessionAwareEventRouter:
    active_session_ids: set[str] | None = None
    destination_registry: RouteDestinationRegistry | None = None

    def route(self, event: StandardizedEvent) -> EventRouteResult:
        active_session_ids = self.active_session_ids or set()

        session_id = self._session_id_for(event)
        if session_id in active_session_ids:
            return EventRouteResult(
                event=event,
                destination=self._destination("SESSION_INBOX"),
                reason="event targets an active task session",
                target_session_id=session_id,
            )

        if event.metadata.get("suppress") is True or event.event_type.endswith("_NOISE"):
            return EventRouteResult(
                event=event,
                destination=self._destination("SUPPRESSED"),
                reason="event marked as suppressed or noise",
            )

        if event.metadata.get("ambient") is True or event.event_type in {
            "ENVIRONMENT_UPDATE",
            "VISUAL_OBSERVATION",
            "AMBIENT_OBSERVATION",
        }:
            return EventRouteResult(
                event=event,
                destination=self._destination("AMBIENT_STATE"),
                reason="event updates ambient state",
            )

        if (
            event.metadata.get("trigger_kind") == "user_initiated"
            or event.event_type == "USER_UTTERANCE"
        ):
            return EventRouteResult(
                event=event,
                destination=self._destination("PRESENCE_QUEUE"),
                reason="event was user initiated",
            )

        return EventRouteResult(
            event=event,
            destination=self._destination("SUPPRESSED"),
            reason="event has no routeable session, ambient, or user-initiated signal",
        )

    def _session_id_for(self, event: StandardizedEvent) -> str | None:
        return event.target_session_id or event.caused_by_task_id

    def _destination(self, destination_name: str) -> RouteDestination:
        registry = self.destination_registry or RouteDestinationRegistry()
        destination = registry.get(destination_name)
        if destination is None:
            raise ValueError(f"route destination is not registered: {destination_name}")
        return destination
