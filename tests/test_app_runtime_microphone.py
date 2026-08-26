from pathlib import Path
from types import SimpleNamespace

from app_runtime import AppRuntime
from events.microphone_source import MicrophoneSourceResult
from events.signal import RawSignal
from tasks.output import UserVisibleAgentOutput


class RecordingMicrophoneSource:
    def __init__(self, result: MicrophoneSourceResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def capture_transcript(self, *, trace_id: str) -> MicrophoneSourceResult:
        self.calls.append(trace_id)
        return self.result


class FailingMicrophoneSource:
    def capture_transcript(self, *, trace_id: str) -> MicrophoneSourceResult:
        raise RuntimeError("sensitive backend failure")


class RecordingEventRuntime:
    def __init__(self) -> None:
        self.signals = []

    def publish(self, signal):
        self.signals.append(signal)
        return SimpleNamespace(
            submitted=True,
            task_handle=SimpleNamespace(task_id="task-microphone"),
            reason="submitted",
        )


class RecordingTaskRuntime:
    def __init__(self) -> None:
        self.task_ids = []

    def get_task(self, task_id: str):
        self.task_ids.append(task_id)
        return SimpleNamespace(state=SimpleNamespace(value="delivered"))

    def result_for(self, task_id: str):
        completion = SimpleNamespace(
            user_visible_output=UserVisibleAgentOutput(
                process={"task_goal": "Respond to the transcript."},
                final_response="你好，很高兴见到你。",
            ),
            tool_results=(),
        )
        return SimpleNamespace(
            completion=completion,
            memory_result=SimpleNamespace(
                memory_path=Path("/tmp/memory.md"),
                action="appended",
            ),
            failure_reason=None,
            stop_reason="completed",
            handle=SimpleNamespace(task_id=task_id),
            task=SimpleNamespace(
                state=SimpleNamespace(value="delivered"),
                active_step_ids=(),
                paused_from_state=None,
                terminal_outcome=None,
                delivery=None,
                goal_state=None,
                terminal_execution_state=None,
                task_local_state={},
            ),
            timing=None,
        )


def transcript_result(text: str = "你好") -> MicrophoneSourceResult:
    return MicrophoneSourceResult(
        raw_signal=RawSignal(
            trace_id="trace-source",
            source="speech_transcript",
            payload={"type": "text", "text": text},
        )
    )


def test_microphone_success_uses_source_once_and_runtime_flow():
    source = RecordingMicrophoneSource(transcript_result())
    event_runtime = RecordingEventRuntime()
    task_runtime = RecordingTaskRuntime()
    statuses = []
    runtime = AppRuntime(
        event_runtime,
        task_runtime,
        microphone_source=source,
    )

    result = runtime.run_microphone_with_display(status_callback=statuses.append)

    assert len(source.calls) == 1
    assert event_runtime.signals[0].source == "cli_input"
    assert event_runtime.signals[0].signal_type == "cli_text"
    assert task_runtime.task_ids == ["task-microphone"]
    assert result.snapshot.user_input == "你好"
    assert result.snapshot.transcript == "你好"
    assert statuses == ["Listening...", "Transcription complete."]


def test_microphone_failure_does_not_submit_task_or_memory():
    source = RecordingMicrophoneSource(
        MicrophoneSourceResult(raw_signal=None, error="permission denied")
    )
    event_runtime = RecordingEventRuntime()
    task_runtime = RecordingTaskRuntime()
    runtime = AppRuntime(
        event_runtime,
        task_runtime,
        microphone_source=source,
    )

    result = runtime.run_microphone_with_display()

    assert len(source.calls) == 1
    assert event_runtime.signals == []
    assert task_runtime.task_ids == []
    assert result.snapshot.transcript is None
    assert result.snapshot.memory_status == "not recorded"
    assert "Microphone input failed" in result.snapshot.final_response
    assert "permission denied" not in result.snapshot.final_response


def test_empty_transcript_is_not_submitted():
    source = RecordingMicrophoneSource(transcript_result("   "))
    event_runtime = RecordingEventRuntime()
    task_runtime = RecordingTaskRuntime()
    runtime = AppRuntime(
        event_runtime,
        task_runtime,
        microphone_source=source,
    )

    result = runtime.run_microphone_with_display()

    assert event_runtime.signals == []
    assert task_runtime.task_ids == []
    assert "no speech was detected" in result.snapshot.final_response.lower()


def test_unexpected_microphone_failure_is_safely_contained():
    event_runtime = RecordingEventRuntime()
    task_runtime = RecordingTaskRuntime()
    runtime = AppRuntime(
        event_runtime,
        task_runtime,
        microphone_source=FailingMicrophoneSource(),
    )

    result = runtime.run_microphone_with_display()

    assert event_runtime.signals == []
    assert task_runtime.task_ids == []
    assert "Microphone input failed" in result.snapshot.final_response
    assert "sensitive backend failure" not in result.snapshot.final_response


def test_text_execution_remains_available_after_microphone_failure():
    source = RecordingMicrophoneSource(
        MicrophoneSourceResult(raw_signal=None, error="device busy")
    )
    event_runtime = RecordingEventRuntime()
    task_runtime = RecordingTaskRuntime()
    runtime = AppRuntime(
        event_runtime,
        task_runtime,
        microphone_source=source,
    )

    runtime.run_microphone_with_display()
    text_result = runtime.run_text_with_display("hello")

    assert text_result.snapshot.user_input == "hello"
    assert len(event_runtime.signals) == 1
