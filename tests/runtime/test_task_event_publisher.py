from datetime import datetime, timezone

from events import StandardizedEvent
from runtime.task_events import TaskEventPublisher
from tasks.task import Task, TaskState


def _task() -> Task:
    event = StandardizedEvent(
        trace_id="trace-events",
        source="test",
        timestamp=datetime.now(timezone.utc),
        payload={"text": "observe the screen"},
        event_type="USER_UTTERANCE",
        metadata={},
    )
    return Task(
        task_id="task-events",
        trace_id=event.trace_id,
        source_event=event,
    )


def test_checkpoint_events_have_monotonic_ids_and_state_transitions():
    publisher = TaskEventPublisher()
    task = _task()
    created = publisher.publish_checkpoint(task)
    task.transition_to(TaskState.FORMULATING)
    changed = publisher.publish_checkpoint(task)

    assert created.event_type == "task_created"
    assert changed.event_type == "task_state_changed"
    assert changed.event_id > created.event_id
    assert changed.payload["previous_state"] == "created"
    assert changed.payload["current_state"] == "formulating"


def test_same_checkpoint_state_and_terminal_event_are_deduplicated():
    publisher = TaskEventPublisher()
    task = _task()
    publisher.publish_checkpoint(task)
    assert publisher.publish_checkpoint(task) is None
    task.state = TaskState.KILLED
    publisher.publish_checkpoint(task)

    assert publisher.publish_terminal(task) is not None
    assert publisher.publish_terminal(task) is None


def test_events_after_supports_reconnect_cursor():
    publisher = TaskEventPublisher()
    first = publisher.publish("task_progress", "task", {"index": 1})
    second = publisher.publish("task_progress", "task", {"index": 2})

    assert publisher.events_after(first.event_id) == (second,)
    assert publisher.latest_event_id == second.event_id


def test_delivered_state_emits_a_new_terminal_event():
    publisher = TaskEventPublisher()
    task = _task()
    task.state = TaskState.SUCCEEDED
    succeeded = publisher.publish_terminal(task)
    task.transition_to(TaskState.DELIVERED)
    delivered = publisher.publish_terminal(task)

    assert succeeded is not None
    assert delivered is not None
    assert delivered.payload["state"] == "delivered"
