from devices.microphone import DeviceError
from devices.screen import (
    MockScreenProvider,
    RealScreenProvider,
    ScreenBackendError,
)


def test_mock_screen_provider_returns_image_payload():
    result = MockScreenProvider().capture_screen(task_id="task-screen")

    assert result.succeeded is True
    assert result.device_name == "mock_screen"
    assert result.task_id == "task-screen"
    assert result.output == {
        "type": "image",
        "frame": "mock-screen-frame",
        "mime_type": "image/png",
        "source": "screen",
        "scene_summary": "Mock screen shows an Ella web page.",
    }


def test_real_screen_provider_uses_backend_without_opening_on_import():
    backend = RecordingScreenBackend()
    provider = RealScreenProvider(backend=backend)

    result = provider.capture_screen(task_id="task-real")

    assert result.succeeded is True
    assert backend.capture_count == 1
    assert result.output == {
        "type": "image",
        "bytes": b"png-bytes",
        "mime_type": "image/png",
        "source": "screen",
    }
    assert result.metadata["real_device_requested"] is True


def test_real_screen_provider_maps_backend_errors():
    provider = RealScreenProvider(
        backend=FailingScreenBackend(
            ScreenBackendError(
                "permission_denied",
                "screen capture permission was denied",
            )
        )
    )

    result = provider.capture_screen(task_id="task-fail")

    assert result.failed is True
    assert result.error == DeviceError(
        device_name="desktop_screen",
        message="screen capture permission was denied",
        code="permission_denied",
        metadata={"device_kind": "screen"},
    )


class RecordingScreenBackend:
    def __init__(self) -> None:
        self.capture_count = 0

    def capture_png(self) -> bytes:
        self.capture_count += 1
        return b"png-bytes"


class FailingScreenBackend:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def capture_png(self) -> bytes:
        raise self.error
