from dataclasses import dataclass, field
from typing import Any

from devices.microphone import MicrophoneProvider, MockMicrophoneProvider
from events.signal import RawSignal
from providers.mock import MockSpeechProvider
from providers.speech import SpeechProvider


@dataclass(frozen=True, slots=True)
class MicrophoneSourceResult:
    raw_signal: RawSignal | None
    submitted: bool = False
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MicrophoneSource:
    microphone_provider: MicrophoneProvider = field(
        default_factory=MockMicrophoneProvider
    )
    speech_provider: SpeechProvider = field(default_factory=MockSpeechProvider)

    def capture_transcript(self, *, trace_id: str) -> MicrophoneSourceResult:
        microphone_result = self.microphone_provider.capture(trace_id=trace_id)
        if microphone_result.failed:
            return MicrophoneSourceResult(
                raw_signal=None,
                error=(
                    "microphone capture failed: "
                    f"{microphone_result.error.message}"
                ),
                metadata=self._metadata(),
            )

        speech_result = self.speech_provider.transcribe(
            microphone_result.output,
            trace_id=trace_id,
        )
        if speech_result.failed:
            return MicrophoneSourceResult(
                raw_signal=None,
                error=(
                    "speech transcription failed: "
                    f"{speech_result.error.message}"
                ),
                metadata=self._metadata(),
            )

        text = speech_result.output["text"]
        return MicrophoneSourceResult(
            raw_signal=RawSignal(
                trace_id=trace_id,
                source="speech_transcript",
                payload={
                    "type": "text",
                    "text": text,
                },
            ),
            metadata=self._metadata(),
        )

    def _metadata(self) -> dict[str, Any]:
        return {
            "microphone_provider": self.microphone_provider.device_name,
            "speech_provider": self.speech_provider.provider_name,
        }
