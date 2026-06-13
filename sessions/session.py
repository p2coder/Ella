from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from agent.handoff import HandoffRequest


class TaskState(StrEnum):
    CREATED = "created"


@dataclass(slots=True)
class TaskSession:
    session_id: str
    task_id: str
    handoff: HandoffRequest
    state: TaskState = TaskState.CREATED
    task_local_state: dict[str, Any] = field(default_factory=dict)
    message_history: tuple[dict[str, Any], ...] = ()
    tool_trace: tuple[dict[str, Any], ...] = ()

    def set_task_state(self, key: str, value: Any) -> None:
        self.task_local_state[key] = value
