from types import SimpleNamespace
from urllib.parse import urlencode

from demo.web_ui import LocalWebUI, render_web_ui_shell


class ControlAppRuntime:
    def __init__(self, state="running"):
        self.state = state
        self.calls = []

    def get_task(self, task_id):
        if task_id != "task-1":
            raise KeyError(task_id)
        return {
            "state": self.state,
            "waiting_condition": None,
            "paused_from_state": "running" if self.state == "paused" else None,
            "terminal_outcome": None,
        }

    def pause(self, task_id, reason=""):
        self.calls.append(("pause", task_id))
        self.state = "paused"
        return SimpleNamespace(accepted=True, message="accepted")

    def resume(self, task_id, reason=""):
        self.calls.append(("resume", task_id))
        self.state = "ready"
        return SimpleNamespace(accepted=True, message="accepted")

    def kill(self, task_id, reason=""):
        self.calls.append(("kill", task_id))
        self.state = "killed"
        return SimpleNamespace(accepted=True, message="accepted")

    def run_submitted_task_with_display(self, task_id, *, user_input):
        raise RuntimeError("task did not complete: paused")


def _control_request(web_ui, action):
    return web_ui.handle_request(
        method="POST",
        path="/task/control",
        body=urlencode({"task_id": "task-1", "action": action}).encode(),
        content_type="application/x-www-form-urlencoded",
    )


def test_task_state_and_control_buttons_are_rendered():
    html = render_web_ui_shell({"task_id": "task-1", "task_state": "running"})

    assert 'data-task-state="running"' in html
    assert 'data-task-action="pause"' in html
    assert 'data-task-action="resume" disabled' in html
    assert 'data-task-action="kill"' in html


def test_only_paused_task_enables_resume_and_disables_pause():
    html = render_web_ui_shell({"task_id": "task-1", "task_state": "paused"})

    assert 'data-task-action="pause" disabled' in html
    assert 'data-task-action="resume" ' in html


def test_pause_requested_disables_pause_and_kill():
    html = render_web_ui_shell(
        {"task_id": "task-1", "task_state": "pause_requested"}
    )

    assert 'data-task-action="pause" disabled' in html
    assert 'data-task-action="kill" disabled' in html


def test_web_control_endpoint_calls_app_runtime_only():
    app = ControlAppRuntime()
    web_ui = LocalWebUI(app)

    paused = _control_request(web_ui, "pause")
    resumed = _control_request(web_ui, "resume")
    killed = _control_request(web_ui, "kill")

    assert paused.status == resumed.status == killed.status == 200
    assert app.calls == [
        ("pause", "task-1"),
        ("resume", "task-1"),
        ("kill", "task-1"),
    ]


def test_task_status_endpoint_projects_current_state():
    response = LocalWebUI(ControlAppRuntime("paused")).handle_request(
        method="GET",
        path="/task?task_id=task-1",
    )

    assert response.status == 200
    assert 'data-task-state="paused"' in response.body
