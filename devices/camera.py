import importlib
import sys
from dataclasses import dataclass, field
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


class CameraBackendError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class CameraCapture(Protocol):
    def is_opened(self) -> bool:
        ...

    def read(self) -> tuple[bool, Any]:
        ...

    def release(self) -> None:
        ...


class CameraBackend(Protocol):
    def open(self, device: int | str, timeout_seconds: float) -> CameraCapture:
        ...

    def encode_jpeg(self, frame: Any) -> bytes:
        ...


@dataclass(slots=True)
class _OpenCVCapture:
    capture: Any

    def is_opened(self) -> bool:
        return bool(self.capture.isOpened())

    def read(self) -> tuple[bool, Any]:
        return self.capture.read()

    def release(self) -> None:
        self.capture.release()


@dataclass(frozen=True, slots=True)
class OpenCVCameraBackend:
    def open(self, device: int | str, timeout_seconds: float) -> CameraCapture:
        try:
            cv2 = importlib.import_module("cv2")
        except ImportError:
            raise CameraBackendError(
                "backend_unavailable",
                "real camera provider is not wired yet",
            ) from None

        try:
            capture = self._video_capture(cv2, device)
            timeout_ms = int(timeout_seconds * 1000)
            for property_name in (
                "CAP_PROP_OPEN_TIMEOUT_MSEC",
                "CAP_PROP_READ_TIMEOUT_MSEC",
            ):
                property_id = getattr(cv2, property_name, None)
                if property_id is not None:
                    capture.set(property_id, timeout_ms)
        except PermissionError:
            raise
        except Exception as error:
            raise self._mapped_error(error) from None

        wrapped = _OpenCVCapture(capture)
        if not wrapped.is_opened():
            wrapped.release()
            raise CameraBackendError(
                "device_not_found",
                "camera device could not be opened",
            )
        return wrapped

    def encode_jpeg(self, frame: Any) -> bytes:
        cv2 = importlib.import_module("cv2")
        try:
            succeeded, encoded = cv2.imencode(".jpg", frame)
        except Exception as error:
            raise self._mapped_error(error) from None
        if not succeeded:
            raise CameraBackendError(
                "backend_failure",
                "camera frame JPEG encoding failed",
            )
        return encoded.tobytes()

    @staticmethod
    def _video_capture(cv2: Any, device: int | str) -> Any:
        if sys.platform == "darwin" and hasattr(cv2, "CAP_AVFOUNDATION"):
            return cv2.VideoCapture(device, cv2.CAP_AVFOUNDATION)
        if sys.platform == "win32" and hasattr(cv2, "CAP_DSHOW"):
            return cv2.VideoCapture(device, cv2.CAP_DSHOW)
        return cv2.VideoCapture(device)

    @staticmethod
    def _mapped_error(error: Exception) -> CameraBackendError:
        message = str(error).lower()
        if "permission" in message or "authorized" in message:
            return CameraBackendError(
                "permission_denied",
                "camera permission was denied",
            )
        if "busy" in message or "in use" in message:
            return CameraBackendError("device_busy", "camera device is busy")
        if "timeout" in message or "timed out" in message:
            return CameraBackendError("timeout", "camera capture timed out")
        return CameraBackendError("backend_failure", "camera backend failed")


@dataclass(frozen=True, slots=True)
class RealCameraProvider:
    camera_device: str | int = "default"
    timeout_seconds: float = 5.0
    backend: CameraBackend = field(default_factory=OpenCVCameraBackend)
    device_name: str = "opencv_camera"

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("camera timeout_seconds must be greater than zero")

    def capture_frame(
        self,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceResult:
        capture: CameraCapture | None = None
        try:
            capture = self.backend.open(
                self._resolved_device(),
                self.timeout_seconds,
            )
            if not capture.is_opened():
                raise CameraBackendError(
                    "device_not_found",
                    "camera device could not be opened",
                )
            succeeded, frame = capture.read()
            if not succeeded or frame is None:
                raise CameraBackendError(
                    "backend_failure",
                    "camera did not return a frame",
                )
            encoded = self.backend.encode_jpeg(frame)
        except Exception as error:
            return self._error_result(error, trace_id, metadata)
        finally:
            if capture is not None:
                capture.release()

        return DeviceResult(
            device_name=self.device_name,
            trace_id=trace_id,
            output={
                "type": "image",
                "bytes": encoded,
                "mime_type": "image/jpeg",
            },
            metadata={
                **dict(metadata or {}),
                "real_device_requested": True,
                "camera_device": str(self.camera_device),
            },
        )

    def _resolved_device(self) -> int | str:
        if self.camera_device == "default":
            return 0
        if isinstance(self.camera_device, int):
            return self.camera_device
        normalized = self.camera_device.strip()
        if normalized.isdigit():
            return int(normalized)
        return normalized

    def _error_result(
        self,
        error: Exception,
        trace_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> DeviceResult:
        if isinstance(error, CameraBackendError):
            code = error.code
            message = str(error)
        elif isinstance(error, PermissionError):
            code = "permission_denied"
            message = "camera permission was denied"
        elif isinstance(error, TimeoutError):
            code = "timeout"
            message = "camera capture timed out"
        else:
            code = "backend_failure"
            message = "camera backend failed"

        error_metadata = {
            "device_kind": "camera",
            "device_name": str(self.camera_device),
        }
        return DeviceResult(
            device_name=self.device_name,
            trace_id=trace_id,
            output=None,
            metadata={"real_device_requested": True, **dict(metadata or {})},
            error=DeviceError(
                device_name=self.device_name,
                message=message,
                code=code,
                metadata=error_metadata,
            ),
        )


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
