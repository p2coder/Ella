from devices.microphone import DeviceResult, MockMicrophoneProvider
from events.microphone_source import MicrophoneSource
from providers.base import ProviderResult
from providers.mock import MockSpeechProvider


class CountingMicrophoneProvider:
    device_name = "counting_microphone"

    def __init__(self):
        self.capture_calls = 0

    def capture(self, *, task_id=None, metadata=None):
        self.capture_calls += 1
        return DeviceResult(
            device_name=self.device_name,
            task_id=task_id,
            output={
                "type": "audio",
                "bytes": b"bounded-audio",
                "mime_type": "audio/L16",
                "sample_format": "int16",
                "sample_rate": 16_000,
                "channels": 1,
                "duration_seconds": 5,
            },
        )


class CountingSpeechProvider:
    provider_name = "counting_speech"
    model_name = "counting-speech"

    def __init__(self):
        self.transcribe_calls = 0

    def transcribe(self, audio, *, task_id=None, metadata=None):
        self.transcribe_calls += 1
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            task_id=task_id,
            output={"text": "Ella，我要出门了"},
        )


class FakeDeviceFactory:
    def __init__(self, microphone_provider):
        self.microphone_provider = microphone_provider
        self.microphone_calls = 0

    def microphone(self):
        self.microphone_calls += 1
        return self.microphone_provider


class FakeProviderFactory:
    def __init__(self, speech_provider):
        self.speech_provider = speech_provider
        self.speech_calls = 0

    def speech(self):
        self.speech_calls += 1
        return self.speech_provider


def test_from_factories_assembles_configured_dependencies_without_capture():
    microphone = CountingMicrophoneProvider()
    speech = CountingSpeechProvider()
    device_factory = FakeDeviceFactory(microphone)
    provider_factory = FakeProviderFactory(speech)

    source = MicrophoneSource.from_factories(
        device_factory=device_factory,
        provider_factory=provider_factory,
    )

    assert source.microphone_provider is microphone
    assert source.speech_provider is speech
    assert device_factory.microphone_calls == 1
    assert provider_factory.speech_calls == 1
    assert microphone.capture_calls == 0
    assert speech.transcribe_calls == 0


def test_factory_assembled_source_performs_one_bounded_capture_and_transcription():
    microphone = CountingMicrophoneProvider()
    speech = CountingSpeechProvider()
    source = MicrophoneSource.from_factories(
        device_factory=FakeDeviceFactory(microphone),
        provider_factory=FakeProviderFactory(speech),
    )

    result = source.capture_transcript(task_id="task-configured-mic")

    assert microphone.capture_calls == 1
    assert speech.transcribe_calls == 1
    assert result.error is None
    assert result.raw_signal.source == "speech_transcript"
    assert result.raw_signal.payload == {
        "type": "text",
        "text": "Ella，我要出门了",
    }


def test_from_factories_uses_mock_safe_defaults():
    source = MicrophoneSource.from_factories()

    assert isinstance(source.microphone_provider, MockMicrophoneProvider)
    assert isinstance(source.speech_provider, MockSpeechProvider)


def test_direct_dependency_injection_remains_supported():
    microphone = CountingMicrophoneProvider()
    speech = CountingSpeechProvider()

    source = MicrophoneSource(
        microphone_provider=microphone,
        speech_provider=speech,
    )

    assert source.microphone_provider is microphone
    assert source.speech_provider is speech
