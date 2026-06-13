from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .microphone import DeviceError, DeviceResult


@runtime_checkable
class CameraProvider(Protocol):
    device_name: str

    def capture_frame(
        self,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceResult:
        ...


@dataclass(frozen=True, slots=True)
class MockCameraProvider:
    device_name: str = "mock_camera"
    scene_summary: str = "Mock camera frame contains phone, keys, and wallet."

    def capture_frame(
        self,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceResult:
        return DeviceResult(
            device_name=self.device_name,
            trace_id=trace_id,
            output={
                "type": "image",
                "frame": "mock-camera-frame",
                "scene_summary": self.scene_summary,
            },
            metadata={"mock": True, **dict(metadata or {})},
        )


@dataclass(frozen=True, slots=True)
class UnavailableCameraProvider:
    device_name: str = "unavailable_camera"
    reason: str = "real camera provider is not wired yet"
    device_label: str = "default"
    enabled_flag: str | None = None

    def capture_frame(
        self,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceResult:
        error_metadata = {"device_kind": "camera"}
        if self.enabled_flag is not None:
            error_metadata["enabled_flag"] = self.enabled_flag
        else:
            error_metadata["device_name"] = self.device_label

        return DeviceResult(
            device_name=self.device_name,
            trace_id=trace_id,
            output=None,
            metadata={"real_device_requested": True, **dict(metadata or {})},
            error=DeviceError(
                device_name=self.device_name,
                message=self.reason,
                code="device_unavailable",
                metadata=error_metadata,
            ),
        )
