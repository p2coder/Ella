from dataclasses import dataclass
from pathlib import Path

from demo.cli_demo import DemoRuntime, run_demo
from events.microphone_source import MicrophoneSourceResult
from events.signal import RawSignal
from memory import MemoryWriteResult
from runtime.event_runtime import EventRuntimeResult
from runtime.task_runtime import TaskHandle
from sessions.completion import TaskCompletionPackage
from sessions.output import UserVisibleAgentOutput


@dataclass
class RecordingEventRuntime:
    published: list

    def publish(self, signal):
        self.published.append(signal)
        return EventRuntimeResult(
            event=None,
            route=None,
            submitted=True,
            task_handle=TaskHandle("task-mic", "session-mic", signal.trace_id),
            reason="submitted",
        )


class CompletingTaskRuntime:
    def __init__(self, memory_path: Path):
        self.memory_path = memory_path
        self.calls = []

    def run_until_complete(self, task_id, max_steps):
        self.calls.append((task_id, max_steps))
        completion = TaskCompletionPackage(
            context=None,
            summary="Completed through runtime.",
            user_visible_output=UserVisibleAgentOutput(
                process={"status": "Runtime handled microphone input."},
                final_response="Microphone task complete.",
            ),
            tool_results=(),
        )
        return StubTaskRuntimeResult(
            completion=completion,
            memory_result=MemoryWriteResult("appended", self.memory_path),
        )


@dataclass(frozen=True)
class StubTaskRuntimeResult:
    completion: TaskCompletionPackage
    memory_result: MemoryWriteResult
    failure_reason: str | None = None


class SuccessfulMicrophoneSource:
    def __init__(self):
        self.calls = []

    def capture_transcript(self, *, trace_id):
        self.calls.append(trace_id)
        return MicrophoneSourceResult(
            raw_signal=RawSignal(
                trace_id=trace_id,
                source="speech_transcript",
                payload={"type": "text", "text": "Ella，我要出门了"},
            )
        )


class FailingMicrophoneSource:
    def capture_transcript(self, *, trace_id):
        return MicrophoneSourceResult(
            raw_signal=None,
            error="microphone capture failed: device unavailable",
        )


def make_runtime(tmp_path):
    event_runtime = RecordingEventRuntime([])
    task_runtime = CompletingTaskRuntime(tmp_path / "memory.md")
    return DemoRuntime(event_runtime, task_runtime), event_runtime, task_runtime


def test_microphone_mode_captures_once_and_publishes_transcript_signal(tmp_path):
    runtime, event_runtime, task_runtime = make_runtime(tmp_path)
    microphone_source = SuccessfulMicrophoneSource()
    statuses = []

    output = runtime.run_input(
        mode="microphone",
        microphone_source=microphone_source,
        status_callback=statuses.append,
    )

    assert microphone_source.calls == ["trace-cli-microphone"]
    assert len(event_runtime.published) == 1
    assert event_runtime.published[0].source == "speech_transcript"
    assert event_runtime.published[0].payload == {
        "type": "text",
        "text": "Ella，我要出门了",
    }
    assert task_runtime.calls == [("task-mic", 20)]
    assert statuses == ["Listening...", "Transcription complete."]
    assert "[Ella Process]" in output
    assert "Microphone task complete." in output


def test_microphone_failure_returns_fallback_without_publishing(tmp_path):
    runtime, event_runtime, task_runtime = make_runtime(tmp_path)
    statuses = []

    output = runtime.run_input(
        mode="microphone",
        microphone_source=FailingMicrophoneSource(),
        status_callback=statuses.append,
    )

    assert event_runtime.published == []
    assert task_runtime.calls == []
    assert statuses[0] == "Listening..."
    assert "device unavailable" in output
    assert "Text input remains available." in output


def test_text_mode_remains_available_after_microphone_failure(tmp_path):
    runtime, event_runtime, task_runtime = make_runtime(tmp_path)
    runtime.run_input(
        mode="microphone",
        microphone_source=FailingMicrophoneSource(),
    )

    output = runtime.run_input(mode="text", input_text="Ella，我要出门了")

    assert len(event_runtime.published) == 1
    assert event_runtime.published[0].source == "cli_input"
    assert task_runtime.calls == [("task-mic", 20)]
    assert "[Final Answer]" in output


def test_run_demo_remains_non_interactive_text_mode(tmp_path):
    runtime, event_runtime, _ = make_runtime(tmp_path)

    output = run_demo(input_text="Ella，我要出门了", runtime=runtime)

    assert len(event_runtime.published) == 1
    assert event_runtime.published[0].source == "cli_input"
    assert "[Memory]" in output
