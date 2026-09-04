from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Condition
from typing import Any, Mapping

from tasks.task import Task, TaskState


TERMINAL_TASK_STATES = frozenset(
    {
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.UNCERTAIN,
        TaskState.KILLED,
        TaskState.DELIVERED,
    }
)


@dataclass(frozen=True, slots=True)
class TaskEvent:
    event_id: int
    event_type: str
    task_id: str
    payload: Mapping[str, Any]
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "task_id": self.task_id,
            "payload": dict(self.payload),
            "recorded_at": self.recorded_at,
        }


@dataclass(slots=True)
class TaskEventPublisher:
    max_events: int = 2_000
    _events: deque[TaskEvent] = field(init=False, repr=False)
    _condition: Condition = field(init=False, repr=False)
    _next_event_id: int = field(init=False, default=1, repr=False)
    _states: dict[str, str] = field(init=False, repr=False)
    _terminal_published: set[tuple[str, str]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._events = deque(maxlen=self.max_events)
        self._condition = Condition()
        self._states = {}
        self._terminal_published = set()

    def publish_checkpoint(self, task: Task) -> TaskEvent | None:
        state = task.state.value
        previous = self._states.get(task.task_id)
        if previous == state:
            return None
        self._states[task.task_id] = state
        if previous is None:
            return self.publish(
                "task_created",
                task.task_id,
                {
                    "state": state,
                    "goal_state": _goal_state(task),
                    "terminal_execution_state": _terminal_execution_state(task),
                    "task_id": task.task_id,
                    "user_input_summary": _user_input_summary(task),
                },
            )
        return self.publish(
            "task_state_changed",
            task.task_id,
            {
                "previous_state": previous,
                "current_state": state,
                "goal_state": _goal_state(task),
                "terminal_execution_state": _terminal_execution_state(task),
                "updated_at": task.updated_at.isoformat(),
            },
        )

    def publish_progress(
        self,
        task: Task,
        *,
        execution_stage: str,
        tool_name: str | None = None,
    ) -> TaskEvent:
        return self.publish(
            "task_progress",
            task.task_id,
            {
                "state": task.state.value,
                "goal_state": _goal_state(task),
                "terminal_execution_state": _terminal_execution_state(task),
                "execution_stage": execution_stage,
                "tool_name": tool_name,
            },
        )

    def publish_terminal(
        self,
        task: Task,
        *,
        memory_status: str | None = None,
    ) -> TaskEvent | None:
        if task.state not in TERMINAL_TASK_STATES:
            return None
        terminal_key = (task.task_id, task.state.value)
        with self._condition:
            if terminal_key in self._terminal_published:
                return None
            self._terminal_published.add(terminal_key)
        completion = task.completion
        final_response = None
        if completion is not None:
            final_response = completion.user_visible_output.final_response
        return self.publish(
            "task_terminal",
            task.task_id,
            {
                "state": task.state.value,
                "goal_state": _goal_state(task),
                "terminal_execution_state": _terminal_execution_state(task),
                "finished_at": task.updated_at.isoformat(),
                "final_response": final_response,
                "failure": task.failure,
                "terminal_outcome": task.terminal_outcome,
                "memory_status": memory_status,
            },
        )

    def publish(
        self,
        event_type: str,
        task_id: str,
        payload: Mapping[str, Any],
    ) -> TaskEvent:
        with self._condition:
            event = TaskEvent(
                self._next_event_id,
                event_type,
                task_id,
                dict(payload),
                datetime.now(timezone.utc).isoformat(),
            )
            self._next_event_id += 1
            self._events.append(event)
            self._condition.notify_all()
            return event

    def events_after(self, event_id: int | None) -> tuple[TaskEvent, ...]:
        boundary = 0 if event_id is None else event_id
        with self._condition:
            return tuple(
                event for event in self._events if event.event_id > boundary
            )

    @property
    def latest_event_id(self) -> int:
        with self._condition:
            return self._next_event_id - 1

    def wait_after(
        self,
        event_id: int | None,
        *,
        timeout: float = 15.0,
    ) -> tuple[TaskEvent, ...]:
        events = self.events_after(event_id)
        if events:
            return events
        with self._condition:
            self._condition.wait(timeout)
            boundary = 0 if event_id is None else event_id
            return tuple(
                event for event in self._events if event.event_id > boundary
            )


def _user_input_summary(task: Task, maximum: int = 120) -> str:
    event = task.source_event
    if event is None:
        return ""
    text = str(event.payload.get("text", "")).strip()
    return text if len(text) <= maximum else f"{text[: maximum - 1]}…"


def _goal_state(task: Task) -> str | None:
    return None if task.goal_state is None else task.goal_state.value


def _terminal_execution_state(task: Task) -> str | None:
    state = task.terminal_execution_state
    return None if state is None else state.value
