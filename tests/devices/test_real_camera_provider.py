import inspect

import pytest

from devices.camera import CameraBackendError, RealCameraProvider


class FakeCapture:
    def __init__(self, *, opened=True, read_result=(True, "frame")):
        self.opened = opened
        self.read_result = read_result
        self.released = False

    def is_opened(self):
        return self.opened

    def read(self):
        return self.read_result

    def release(self):
        self.released = True


class FakeBackend:
    def __init__(self, capture=None, error=None):
        self.capture = capture or FakeCapture()
        self.error = error
        self.open_calls = []
        self.encoded_frames = []

    def open(self, device, timeout_seconds):
        self.open_calls.append((device, timeout_seconds))
        if self.error is not None:
            raise self.error
        return self.capture

    def encode_jpeg(self, frame):
        self.encoded_frames.append(frame)
        return b"encoded-jpeg"


def test_real_camera_captures_encoded_frame_and_releases_device():
    backend = FakeBackend()
    provider = RealCameraProvider(
        camera_device="default",
        timeout_seconds=2.5,
        backend=backend,
    )

    result = provider.capture_frame(
        task_id="task-camera",
        metadata={"purpose": "task"},
    )

    assert result.succeeded
    assert result.output == {
        "type": "image",
        "bytes": b"encoded-jpeg",
        "mime_type": "image/jpeg",
    }
    assert result.metadata == {
        "purpose": "task",
        "real_device_requested": True,
        "camera_device": "default",
    }
    assert backend.open_calls == [(0, 2.5)]
    assert backend.encoded_frames == ["frame"]
    assert backend.capture.released is True


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("0", 0), ("2", 2), (2, 2), ("studio-camera", "studio-camera")],
)
def test_real_camera_resolves_default_index_and_explicit_devices(
    configured,
    expected,
):
    backend = FakeBackend()
    provider = RealCameraProvider(camera_device=configured, backend=backend)

    provider.capture_frame()

    assert backend.open_calls[0][0] == expected


def test_real_camera_releases_device_when_read_fails():
    capture = FakeCapture(read_result=(False, None))
    provider = RealCameraProvider(backend=FakeBackend(capture=capture))

    result = provider.capture_frame()

    assert result.failed
    assert result.error.code == "backend_failure"
    assert capture.released is True


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (PermissionError("camera permission denied"), "permission_denied"),
        (TimeoutError("camera timed out"), "timeout"),
        (CameraBackendError("device_busy", "camera is busy"), "device_busy"),
        (
            CameraBackendError("device_not_found", "camera is missing"),
            "device_not_found",
        ),
        (RuntimeError("backend crashed"), "backend_failure"),
    ],
)
def test_real_camera_maps_backend_failures_to_device_errors(
    error,
    expected_code,
):
    provider = RealCameraProvider(backend=FakeBackend(error=error))

    result = provider.capture_frame(task_id="task-error")

    assert result.failed
    assert result.error.code == expected_code
    assert result.task_id == "task-error"


def test_importing_camera_module_does_not_import_or_open_opencv():
    import devices.camera as camera_module

    source = inspect.getsource(camera_module)
    assert "import cv2" not in source.split("class OpenCVCameraBackend", 1)[0]

