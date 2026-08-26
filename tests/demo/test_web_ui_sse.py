import json
from pathlib import Path
from types import SimpleNamespace

from demo.web_ui import LocalWebUI


class _AppRuntime:
    def __init__(self):
        self.inputs = []

    def submit_text(self, text):
        self.inputs.append(text)
        return SimpleNamespace(task_id="task-api", trace_id="trace-api")

    def get_task(self, task_id):
        return {"task_id": task_id, "state": "created"}

    def task_snapshot(self):
        return {"active_tasks": [], "terminal_tasks": []}


def test_json_task_submission_returns_202_without_waiting_for_completion():
    app = _AppRuntime()
    response = LocalWebUI(app).handle_request(
        method="POST",
        path="/tasks",
        body=json.dumps({"input": "hello"}).encode(),
        content_type="application/json",
    )
    document = json.loads(response.body)

    assert response.status == 202
    assert document == {
        "task_id": "task-api",
        "trace_id": "trace-api",
        "state": "created",
        "auto_start": True,
    }
    assert app.inputs == ["hello"]


def test_task_snapshot_endpoint_returns_both_task_lists():
    response = LocalWebUI(_AppRuntime()).handle_request(
        method="GET",
        path="/tasks",
    )
    assert response.status == 200
    assert json.loads(response.body) == {
        "active_tasks": [],
        "terminal_tasks": [],
    }


def test_web_ui_uses_sse_and_has_no_task_polling_loop():
    source = Path("demo/static/web_ui.html").read_text(encoding="utf-8")
    assert 'new EventSource("/task-events")' in source
    assert "运行中" in source
    assert "已完成" in source
    assert "失败" in source
    assert '"task_interaction_required"' in source
    assert 'fetch("/tasks/input"' in source
    assert 'id="total-duration"' in source
    assert "renderSelectedTask(task)" in source
    assert "task.timing" in source
    assert 'eventName==="task_terminal"' in source
    assert "selectTask(task.task_id)" in source
    assert "`/task?task_id=${encodeURIComponent(taskId)}`" in source
    assert "scheduleTaskRefresh" not in source
    assert "setTimeout" not in source
