import inspect

import demo.web_ui as web_ui_module
from demo.display_snapshot import TEXT_ONLY, RunDisplaySnapshot
from demo.web_ui import LocalWebUI, render_web_ui_shell


def make_snapshot() -> RunDisplaySnapshot:
    return RunDisplaySnapshot(
        user_input="<你好>",
        transcript="<你好>",
        captured_frame_reference=None,
        image_status=TEXT_ONLY,
        scene_summary="",
        visible_items=(),
        task_goal="Respond to the greeting.",
        final_response_prompt_text="",
        tool_results_summary="",
        final_response="<回答>",
        memory_status="appended",
    )


class RecordingAppRuntime:
    def __init__(self) -> None:
        self.microphone_calls = 0
        self.text_calls = []

    def run_microphone_with_display(self):
        self.microphone_calls += 1
        return type("Result", (), {"snapshot": make_snapshot()})()

    def run_text_with_display(self, text: str):
        self.text_calls.append(text)
        return type("Result", (), {"snapshot": make_snapshot()})()


class RuntimeFailingAfterTranscript:
    def run_microphone_with_display(self):
        raise RuntimeError("task did not complete: max_steps")


def test_post_microphone_calls_only_app_runtime_boundary():
    runtime = RecordingAppRuntime()

    response = LocalWebUI(runtime).handle_request(
        method="POST",
        path="/microphone",
    )

    assert response.status == 200
    assert runtime.microphone_calls == 1
    assert runtime.text_calls == []
    assert "&lt;你好&gt;" in response.body
    assert "&lt;回答&gt;" in response.body
    assert '<span class="field-label">Transcript</span>' not in response.body


def test_microphone_runtime_failure_is_not_labeled_as_capture_failure():
    response = LocalWebUI(RuntimeFailingAfterTranscript()).handle_request(
        method="POST",
        path="/microphone",
    )

    assert response.status == 500
    assert "Ella could not complete the microphone task" in response.body
    assert "Microphone input failed" not in response.body
    assert "max_steps" in response.body


def test_web_ui_renders_microphone_action_and_pending_behavior():
    html = render_web_ui_shell()

    assert 'id="microphone-button"' in html
    assert "Microphone" in html
    assert 'fetch("/microphone"' in html
    assert 'beginRequest("Listening...")' in html
    assert "submitButton.disabled = true" in html
    assert "microphoneButton.disabled = true" in html
    assert "submitButton.disabled = false" in html
    assert "microphoneButton.disabled = false" in html


def test_web_ui_rebinds_actions_after_rendered_page_replacement():
    html = render_web_ui_shell()

    assert "document.write" not in html
    assert "function bindWebUIInteractions()" in html
    assert "bindWebUIInteractions();" in html
    assert "await replacePage(response);" in html


def test_web_ui_has_no_browser_or_device_microphone_access():
    source = inspect.getsource(web_ui_module)
    template = web_ui_module.TEMPLATE_PATH.read_text(encoding="utf-8")
    combined = source + template

    for forbidden in (
        "MicrophoneSource",
        "DeviceFactory",
        "ProviderFactory",
        "RealMicrophoneProvider",
        "MockMicrophoneProvider",
        "SpeechProvider",
        "navigator.mediaDevices",
        "getUserMedia",
        "MediaRecorder",
        "AudioContext",
        "webkitAudioContext",
    ):
        assert forbidden not in combined


def test_existing_text_submission_still_works():
    runtime = RecordingAppRuntime()

    response = LocalWebUI(runtime).submit_text("hello")

    assert response.status == 200
    assert runtime.text_calls == ["hello"]
