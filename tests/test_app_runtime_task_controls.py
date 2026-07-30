from datetime import datetime, timezone
from types import SimpleNamespace

from app_runtime import AppRuntime
from runtime.task_runtime import TaskHandle
from sessions.execution_state import TaskControlType


class FakeEventRuntime:
    def __init__(self):
        self.published = []

    def publish(self, signal):
        self.published.append(signal)
        return SimpleNamespace(
            submitted=True,
            task_handle=TaskHandle("task-1", signal.trace_id),
            reason="",
        )


class FakeTaskRuntime:
    def __init__(self):
        self.commands = []

    def apply_control(self, command):
        self.commands.append(command)
        return SimpleNamespace(accepted=True, current_state=command.command_type.value)


def _app():
    return AppRuntime(FakeEventRuntime(), FakeTaskRuntime())


def test_submit_text_uses_event_runtime_facade_boundary():
    app = _app()
    handle = app.submit_text("hello")
    assert handle.task_id == "task-1"
    assert app._event_runtime.published[0].payload["text"] == "hello"


def test_pause_resume_and_kill_are_control_commands():
    app = _app()
    app.pause("task")
    app.resume("task")
    app.kill("task")
    assert tuple(command.command_type for command in app._task_runtime.commands) == (
        TaskControlType.PAUSE,
        TaskControlType.RESUME,
        TaskControlType.KILL,
    )


def test_app_runtime_does_not_expose_runtime_components_as_public_properties():
    app = _app()
    assert not hasattr(app, "task_store")
    assert not hasattr(app, "scheduler")
    assert not hasattr(app, "executor")
