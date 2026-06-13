from devices.camera import CameraProvider, MockCameraProvider
from devices.microphone import DeviceError, DeviceResult
from events.camera_source import CameraSource
from events.signal import RawSignal
from providers.base import ProviderError, ProviderResult
from providers.mock import MockVisionProvider


def test_camera_source_returns_camera_raw_signal():
    source = CameraSource(
        camera_provider=MockCameraProvider(),
        vision_provider=MockVisionProvider(scene_summary="Desk with keys."),
    )

    result = source.capture_scene_summary(trace_id="trace-camera")

    assert result.submitted is False
    assert result.error is None
    assert isinstance(result.raw_signal, RawSignal)
    assert result.raw_signal.trace_id == "trace-camera"
    assert result.raw_signal.source == "camera"


def test_camera_source_payload_has_image_summary_and_summary_text():
    source = CameraSource(
        camera_provider=MockCameraProvider(),
        vision_provider=MockVisionProvider(scene_summary="Doorway is clear."),
    )

    result = source.capture_scene_summary(trace_id="trace-summary")

    assert result.raw_signal is not None
    assert result.raw_signal.payload == {
        "type": "image_summary",
        "summary": "Doorway is clear.",
    }


def test_camera_source_does_not_create_task_session_or_call_task_runtime():
    source = CameraSource()

    result = source.capture_scene_summary(trace_id="trace-boundary")

    assert result.raw_signal is not None
    assert result.submitted is False
    assert not hasattr(source, "task_runtime")
    assert not hasattr(source, "task_session_manager")


def test_camera_source_does_not_modify_ambient_state_directly():
    source = CameraSource()

    result = source.capture_scene_summary(trace_id="trace-ambient")

    assert result.raw_signal is not None
    assert not hasattr(source, "ambient_state")
    assert result.metadata["ambient_state_updated"] is False


def test_default_source_uses_mock_providers_without_real_camera_access():
    source = CameraSource()

    result = source.capture_scene_summary(trace_id="trace-default")

    assert result.raw_signal is not None
    assert result.metadata == {
        "camera_provider": "mock_camera",
        "vision_provider": "mock_vision",
        "ambient_state_updated": False,
    }


def test_camera_failure_returns_non_submitted_error_result():
    source = CameraSource(
        camera_provider=FailingCameraProvider(),
        vision_provider=MockVisionProvider(),
    )

    result = source.capture_scene_summary(trace_id="trace-camera-fail")

    assert result.raw_signal is None
    assert result.submitted is False
    assert result.error == "camera capture failed: camera unavailable"


def test_vision_failure_returns_non_submitted_error_result():
    source = CameraSource(
        camera_provider=MockCameraProvider(),
        vision_provider=FailingVisionProvider(),
    )

    result = source.capture_scene_summary(trace_id="trace-vision-fail")

    assert result.raw_signal is None
    assert result.submitted is False
    assert result.error == "vision summary failed: vision unavailable"


class FailingCameraProvider:
    device_name = "failing_camera"

    def capture_frame(self, *, trace_id=None, metadata=None):
        return DeviceResult(
            device_name=self.device_name,
            trace_id=trace_id,
            output=None,
            error=DeviceError(
                device_name=self.device_name,
                message="camera unavailable",
                code="device_unavailable",
            ),
        )


class FailingVisionProvider:
    provider_name = "failing_vision"
    model_name = "failing-vision"

    def describe(self, image, *, trace_id=None, metadata=None):
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=None,
            error=ProviderError(
                provider_name=self.provider_name,
                message="vision unavailable",
                code="provider_unavailable",
            ),
        )
