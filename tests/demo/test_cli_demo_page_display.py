import inspect
from dataclasses import dataclass
from pathlib import Path

from demo.cli_demo import DemoRuntime
from demo.display_snapshot import CAMERA_FRAME, RunDisplaySnapshot
from events.microphone_source import MicrophoneSourceResult
from events.signal import RawSignal
from memory import MemoryWriteResult
from runtime.event_runtime import EventRuntimeResult
from runtime.task_runtime import TaskHandle
from sessions.completion import TaskCompletionPackage
from sessions.output import UserVisibleAgentOutput
from tools import ToolResult


@dataclass
class RecordingEventRuntime:
    published: list

    def publish(self, signal):
        self.published.append(signal)
        return EventRuntimeResult(
            event=None,
            route=None,
            submitted=True,
            task_handle=TaskHandle("task-display", "session-display", signal.trace_id),
            reason="submitted",
        )


@dataclass
class CompletingTaskRuntime:
    memory_path: Path
    calls: list

    def run_until_complete(self, task_id, max_steps):
        self.calls.append((task_id, max_steps))
        completion = TaskCompletionPackage(
            context=None,
            summary="Completed through runtime.",
            user_visible_output=UserVisibleAgentOutput(
                process={
                    "task_goal": "Give the user a short reminder before leaving.",
                    "strategy": "going_out",
                    "tool_results": ("camera_scene",),
                    "task_formulation_prompt_text": "TASK PROMPT",
                    "final_response_prompt_text": "FINAL PROMPT",
                },
                final_response="Remember your phone and keys.",
            ),
            tool_results=(
                ToolResult(
                    tool_name="camera_scene",
                    task_id="task-display",
                    session_id="session-display",
                    trace_id="trace-display",
                    payload={
                        "scene_summary": "Desk scene with phone and keys.",
                        "visible_items": ["phone", "keys"],
                        "captured_frame_reference": "mock://frame-1",
                    },
                ),
            ),
        )
        return StubTaskRuntimeResult(
            completion=completion,
            memory_result=MemoryWriteResult("recorded", self.memory_path),
        )


@dataclass(frozen=True)
class StubTaskRuntimeResult:
    completion: TaskCompletionPackage
    memory_result: MemoryWriteResult
    failure_reason: str | None = None
    stop_reason: str | None = "completed"


class SuccessfulMicrophoneSource:
    def capture_transcript(self, *, trace_id):
        return MicrophoneSourceResult(
            raw_signal=RawSignal(
                trace_id=trace_id,
                source="speech_transcript",
                payload={"type": "text", "text": "Ella，我要出门了"},
            )
        )


def make_runtime(tmp_path):
    event_runtime = RecordingEventRuntime([])
    task_runtime = CompletingTaskRuntime(tmp_path / "memory.md", [])
    return DemoRuntime(event_runtime, task_runtime), event_runtime, task_runtime


def test_demo_can_build_display_snapshot_after_text_run(tmp_path):
    runtime, event_runtime, task_runtime = make_runtime(tmp_path)

    result = runtime.run_with_display("Ella，我要出门了")

    assert len(event_runtime.published) == 1
    assert task_runtime.calls == [("task-display", 20)]
    assert "[Final Answer]" in result.output
    assert isinstance(result.snapshot, RunDisplaySnapshot)
    assert result.snapshot.user_input == "Ella，我要出门了"
    assert result.snapshot.transcript is None
    assert result.snapshot.task_goal == (
        "Give the user a short reminder before leaving."
    )
    assert result.snapshot.final_response == "Remember your phone and keys."


def test_demo_can_build_display_snapshot_after_microphone_run(tmp_path):
    runtime, event_runtime, _ = make_runtime(tmp_path)

    result = runtime.run_input_with_display(
        mode="microphone",
        microphone_source=SuccessfulMicrophoneSource(),
    )

    assert len(event_runtime.published) == 1
    assert event_runtime.published[0].source == "speech_transcript"
    assert result.snapshot.user_input == "Ella，我要出门了"
    assert result.snapshot.transcript == "Ella，我要出门了"
    assert "Transcription complete." in result.output


def test_snapshot_includes_visual_summary_prompt_fields_and_final_response(tmp_path):
    runtime, _, _ = make_runtime(tmp_path)

    result = runtime.run_with_display("Ella，我要出门了")
    snapshot = result.snapshot

    assert snapshot.image_status == CAMERA_FRAME
    assert snapshot.captured_frame_reference == "mock://frame-1"
    assert snapshot.scene_summary == "Desk scene with phone and keys."
    assert snapshot.visible_items == ("phone", "keys")
    assert snapshot.task_formulation_prompt_text == "TASK PROMPT"
    assert snapshot.final_response_prompt_text == "FINAL PROMPT"
    assert snapshot.tool_results_summary == (
        "camera_scene:\n"
        "- captured_frame_reference: mock://frame-1\n"
        "- scene_summary: Desk scene with phone and keys.\n"
        "- visible_items: phone, keys"
    )
    assert snapshot.final_response == "Remember your phone and keys."


def test_demo_uses_page_viewer_to_write_display_page(tmp_path):
    runtime, _, _ = make_runtime(tmp_path)
    page_path = tmp_path / "display.html"

    result = runtime.run_with_display("Ella，我要出门了", page_path=page_path)

    assert result.page_path == page_path
    html = page_path.read_text(encoding="utf-8")
    assert "Prompt Sent to LLM" in html
    assert "Remember your phone and keys." in html


def test_display_path_does_not_bypass_runtime_or_call_internal_services():
    source = inspect.getsource(DemoRuntime.run_with_display)
    source += inspect.getsource(DemoRuntime.run_input_with_display)

    for forbidden in (
        "CameraSceneTool",
        "LLMProvider",
        "TaskSession",
        "MemoryManager",
        "TaskCompletionPackage(",
        "create_handoff",
        "select_strategy",
        ".execute(",
        ".handle(",
    ):
        assert forbidden not in source


def test_python_main_style_run_still_returns_text_output(tmp_path):
    runtime, _, _ = make_runtime(tmp_path)

    output = runtime.run("Ella，我要出门了")

    assert isinstance(output, str)
    assert "[Ella Process]" in output
    assert "[Final Answer]" in output
    assert "[Memory]" in output
