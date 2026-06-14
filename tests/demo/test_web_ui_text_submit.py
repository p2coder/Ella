import inspect
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import demo.web_ui as web_ui_module
from demo.display_snapshot import CAMERA_FRAME, RunDisplaySnapshot
from demo.web_ui import DEFAULT_HOST, LocalWebUI, create_server


def make_snapshot() -> RunDisplaySnapshot:
    return RunDisplaySnapshot(
        user_input="<script>alert('input')</script>",
        transcript=None,
        captured_frame_reference=None,
        image_status=CAMERA_FRAME,
        scene_summary="<b>Phone is visible.</b>",
        visible_items=("<phone>", "keys"),
        task_goal="Check what the user still needs before leaving.",
        task_formulation_prompt_text="<task-prompt>",
        final_response_prompt_text="<final-prompt>",
        tool_results_summary="<tool-summary>",
        final_response="<answer>Take your keys.</answer>",
        memory_status="appended",
    )


@dataclass(frozen=True, slots=True)
class FakeDisplayResult:
    output: str
    snapshot: RunDisplaySnapshot
    page_path: Path | None = None


class RecordingAppRuntime:
    def __init__(self) -> None:
        self.inputs: list[str] = []

    def run_text_with_display(self, input_text: str) -> FakeDisplayResult:
        self.inputs.append(input_text)
        return FakeDisplayResult("CLI output", make_snapshot())


def test_web_ui_submits_text_through_app_runtime_and_renders_snapshot():
    runtime = RecordingAppRuntime()
    web_ui = LocalWebUI(runtime)

    response = web_ui.handle_request(
        method="POST",
        path="/submit",
        body=urlencode({"user_input": "Ella, check my desk"}).encode(),
        content_type="application/x-www-form-urlencoded",
    )

    assert response.status == 200
    assert response.content_type == "text/html; charset=utf-8"
    assert runtime.inputs == ["Ella, check my desk"]
    assert "Phone is visible." in response.body
    assert "Take your keys." in response.body
    assert "appended" in response.body


def test_get_request_renders_empty_shell_without_running_task():
    runtime = RecordingAppRuntime()
    response = LocalWebUI(runtime).handle_request(method="GET", path="/")

    assert response.status == 200
    assert "Prompt Sent to LLM" not in response.body
    assert runtime.inputs == []


def test_submission_requires_non_empty_text():
    runtime = RecordingAppRuntime()
    response = LocalWebUI(runtime).handle_request(
        method="POST",
        path="/submit",
        body=urlencode({"user_input": "   "}).encode(),
        content_type="application/x-www-form-urlencoded",
    )

    assert response.status == 400
    assert "Please enter a message." in response.body
    assert runtime.inputs == []


def test_runtime_failure_returns_rendered_error_page():
    class FailingAppRuntime:
        def run_text_with_display(self, input_text: str):
            raise RuntimeError("task execution failed")

    response = LocalWebUI(FailingAppRuntime()).submit_text("hello")

    assert response.status == 500
    assert "task execution failed" in response.body
    assert 'aria-busy="false"' in response.body


def test_default_server_binding_is_localhost_only(monkeypatch):
    runtime = RecordingAppRuntime()
    addresses = []

    class RecordingServer:
        def __init__(self, address, handler):
            addresses.append(address)
            self.server_address = address

    monkeypatch.setattr(web_ui_module, "ThreadingHTTPServer", RecordingServer)

    server = create_server(runtime, port=8080)

    assert DEFAULT_HOST == "127.0.0.1"
    assert addresses == [("127.0.0.1", 8080)]
    assert server.server_address[0] != "0.0.0.0"


def test_user_and_model_generated_output_is_html_escaped():
    response = LocalWebUI(RecordingAppRuntime()).handle_request(
        method="POST",
        path="/submit",
        body=urlencode({"user_input": "unsafe"}).encode(),
        content_type="application/x-www-form-urlencoded",
    )

    assert "<script>alert('input')</script>" not in response.body
    assert "&lt;script&gt;alert(&#x27;input&#x27;)&lt;/script&gt;" in response.body
    assert "&lt;b&gt;Phone is visible.&lt;/b&gt;" in response.body
    assert "&lt;phone&gt;" in response.body
    assert "&lt;task-prompt&gt;" not in response.body
    assert "&lt;final-prompt&gt;" not in response.body
    assert "&lt;tool-summary&gt;" in response.body
    assert "&lt;answer&gt;Take your keys.&lt;/answer&gt;" in response.body


def test_web_ui_only_depends_on_app_runtime_boundary():
    source = inspect.getsource(web_ui_module)

    assert "from app_runtime import AppRuntime" in source
    assert "EventRuntime" not in source
    assert "TaskRuntime" not in source
    assert "TaskSession" not in source
    assert "CameraSceneTool" not in source
    assert "LLMProvider" not in source
    assert "MemoryManager" not in source
    assert ".run_text_with_display(" in source


def test_html_form_posts_text_to_submit_endpoint():
    html = LocalWebUI(RecordingAppRuntime()).handle_request(
        method="GET",
        path="/",
    ).body

    assert 'method="post"' in html
    assert 'action="/submit"' in html
    assert 'name="user_input"' in html
    assert '<button id="submit-button" type="submit">' in html
    assert "submitButton.disabled = true" in html
    assert 'submitButton.textContent = "Running..."' in html
    assert "await fetch(form.action" in html
    assert "submitButton.disabled = false" in html
    assert 'submitButton.textContent = "Submit"' in html
