from devices.microphone import DeviceError, DeviceResult, MockMicrophoneProvider
from events.microphone_source import MicrophoneSource
from events.signal import RawSignal
from providers.base import ProviderError, ProviderResult
from providers.mock import MockSpeechProvider


def test_microphone_source_returns_speech_transcript_raw_signal():
    source = MicrophoneSource(
        microphone_provider=MockMicrophoneProvider(transcript="Ella，我要出门了"),
        speech_provider=MockSpeechProvider(),
    )

    result = source.capture_transcript(trace_id="trace-mic")

    assert result.submitted is False
    assert result.error is None
    assert isinstance(result.raw_signal, RawSignal)
    assert result.raw_signal.trace_id == "trace-mic"
    assert result.raw_signal.source == "speech_transcript"
    assert result.raw_signal.payload == {
        "type": "text",
        "text": "Ella，我要出门了",
    }


def test_microphone_source_payload_has_text_type_and_transcript_text():
    source = MicrophoneSource(
        microphone_provider=MockMicrophoneProvider(transcript="hello ella"),
        speech_provider=MockSpeechProvider(),
    )

    result = source.capture_transcript(trace_id="trace-text")

    assert result.raw_signal is not None
    assert result.raw_signal.payload["type"] == "text"
    assert result.raw_signal.payload["text"] == "hello ella"


def test_microphone_source_does_not_print_transcript(capsys):
    source = MicrophoneSource(
        microphone_provider=MockMicrophoneProvider(transcript="quiet transcript"),
        speech_provider=MockSpeechProvider(),
    )

    result = source.capture_transcript(trace_id="trace-print")

    assert result.raw_signal is not None
    assert result.raw_signal.payload["text"] == "quiet transcript"
    captured = capsys.readouterr()
    assert captured.out == ""


def test_transcription_failure_returns_non_submitted_error_result():
    source = MicrophoneSource(
        microphone_provider=MockMicrophoneProvider(),
        speech_provider=FailingSpeechProvider(),
    )

    result = source.capture_transcript(trace_id="trace-fail")

    assert result.raw_signal is None
    assert result.submitted is False
    assert result.error == "speech transcription failed: speech unavailable"


def test_microphone_failure_returns_non_submitted_error_result():
    source = MicrophoneSource(
        microphone_provider=FailingMicrophoneProvider(),
        speech_provider=MockSpeechProvider(),
    )

    result = source.capture_transcript(trace_id="trace-mic-fail")

    assert result.raw_signal is None
    assert result.submitted is False
    assert result.error == "microphone capture failed: microphone unavailable"


def test_source_does_not_create_task_session_or_call_task_runtime():
    source = MicrophoneSource(
        microphone_provider=MockMicrophoneProvider(),
        speech_provider=MockSpeechProvider(),
    )

    result = source.capture_transcript(trace_id="trace-boundary")

    assert result.raw_signal is not None
    assert result.submitted is False
    assert not hasattr(source, "task_runtime")
    assert not hasattr(source, "task_session_manager")


def test_default_source_uses_mock_microphone_without_real_device_access():
    source = MicrophoneSource()

    result = source.capture_transcript(trace_id="trace-default")

    assert result.raw_signal is not None
    assert result.metadata == {
        "microphone_provider": "mock_microphone",
        "speech_provider": "mock_speech",
    }


class FailingMicrophoneProvider:
    device_name = "failing_microphone"

    def capture(self, *, trace_id=None, metadata=None):
        return DeviceResult(
            device_name=self.device_name,
            trace_id=trace_id,
            output=None,
            error=DeviceError(
                device_name=self.device_name,
                message="microphone unavailable",
                code="device_unavailable",
            ),
        )


class FailingSpeechProvider:
    provider_name = "failing_speech"
    model_name = "failing-speech"

    def transcribe(self, audio, *, trace_id=None, metadata=None):
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=None,
            error=ProviderError(
                provider_name=self.provider_name,
                message="speech unavailable",
                code="provider_unavailable",
            ),
        )
