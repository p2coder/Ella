import inspect

import pytest

from devices.microphone import MicrophoneBackendError, RealMicrophoneProvider


class FakeBackend:
    def __init__(self, *, audio=b"pcm-audio", error=None):
        self.audio = audio
        self.error = error
        self.record_calls = []
        self.release_calls = 0

    def record(
        self,
        *,
        device,
        duration_seconds,
        sample_rate,
        channels,
        timeout_seconds,
    ):
        self.record_calls.append(
            {
                "device": device,
                "duration_seconds": duration_seconds,
                "sample_rate": sample_rate,
                "channels": channels,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.error is not None:
            raise self.error
        return self.audio

    def release(self):
        self.release_calls += 1


def test_real_microphone_records_bounded_pcm_and_releases_backend():
    backend = FakeBackend(audio=b"bounded-pcm")
    provider = RealMicrophoneProvider(
        microphone_device="default",
        duration_seconds=5,
        sample_rate=16_000,
        channels=1,
        backend=backend,
    )

    result = provider.capture(
        task_id="task-mic",
        metadata={"purpose": "transcription"},
    )

    assert result.succeeded
    assert result.output == {
        "type": "audio",
        "bytes": b"bounded-pcm",
        "mime_type": "audio/L16",
        "sample_format": "int16",
        "sample_rate": 16_000,
        "channels": 1,
        "duration_seconds": 5,
    }
    assert result.metadata == {
        "purpose": "transcription",
        "real_device_requested": True,
        "microphone_device": "default",
    }
    assert backend.record_calls == [
        {
            "device": None,
            "duration_seconds": 5,
            "sample_rate": 16_000,
            "channels": 1,
            "timeout_seconds": 10.0,
        }
    ]
    assert backend.release_calls == 1


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("default", None), ("0", 0), (2, 2), ("studio mic", "studio mic")],
)
def test_real_microphone_resolves_default_index_and_named_devices(
    configured,
    expected,
):
    backend = FakeBackend()
    provider = RealMicrophoneProvider(
        microphone_device=configured,
        backend=backend,
    )

    provider.capture()

    assert backend.record_calls[0]["device"] == expected


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (PermissionError("permission denied"), "permission_denied"),
        (TimeoutError("recording timed out"), "timeout"),
        (
            MicrophoneBackendError("device_busy", "microphone is busy"),
            "device_busy",
        ),
        (
            MicrophoneBackendError(
                "device_not_found",
                "microphone is missing",
            ),
            "device_not_found",
        ),
        (RuntimeError("backend failed"), "backend_failure"),
    ],
)
def test_real_microphone_maps_failures_and_always_releases(
    error,
    expected_code,
):
    backend = FakeBackend(error=error)
    provider = RealMicrophoneProvider(backend=backend)

    result = provider.capture(task_id="task-error")

    assert result.failed
    assert result.error.code == expected_code
    assert result.task_id == "task-error"
    assert backend.release_calls == 1


def test_real_microphone_rejects_unbounded_or_invalid_capture_settings():
    with pytest.raises(ValueError, match="duration_seconds"):
        RealMicrophoneProvider(duration_seconds=0)
    with pytest.raises(ValueError, match="sample_rate"):
        RealMicrophoneProvider(sample_rate=0)
    with pytest.raises(ValueError, match="channels"):
        RealMicrophoneProvider(channels=0)


def test_importing_microphone_module_does_not_import_or_open_sounddevice():
    import devices.microphone as microphone_module

    source = inspect.getsource(microphone_module)
    before_backend = source.split("class SoundDeviceMicrophoneBackend", 1)[0]
    assert "import sounddevice" not in before_backend

