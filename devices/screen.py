import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .microphone import DeviceError, DeviceResult


@runtime_checkable
class ScreenProvider(Protocol):
    device_name: str

    def capture_screen(
        self,
        *,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceResult:
        ...


class ScreenBackendError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ScreenBackend(Protocol):
    def capture_png(self) -> bytes:
        ...


@dataclass(frozen=True, slots=True)
class MacOSScreencaptureBackend:
    timeout_seconds: float = 5.0

    def capture_png(self) -> bytes:
        if sys.platform != "darwin":
            raise ScreenBackendError(
                "backend_unavailable",
                "screen capture is only wired for macOS in this build",
            )

        output_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as file:
                output_path = Path(file.name)
            completed = subprocess.run(
                ["screencapture", "-x", "-t", "png", str(output_path)],
                check=False,
                capture_output=True,
                timeout=self.timeout_seconds,
            )
            if completed.returncode != 0:
                raise self._mapped_error(completed.stderr.decode("utf-8", "ignore"))
            data = output_path.read_bytes()
            if not data:
                raise ScreenBackendError(
                    "backend_failure",
                    "screen capture returned an empty image",
                )
            return data
        except subprocess.TimeoutExpired:
            raise ScreenBackendError(
                "timeout",
                "screen capture timed out",
            ) from None
        except PermissionError:
            raise
        except ScreenBackendError:
            raise
        except Exception as error:
            raise ScreenBackendError(
                "backend_failure",
                "screen capture backend failed",
            ) from error
        finally:
            if output_path is not None:
                try:
                    output_path.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _mapped_error(stderr: str) -> ScreenBackendError:
        message = stderr.lower()
        if "permission" in message or "not authorized" in message:
            return ScreenBackendError(
                "permission_denied",
                "screen capture permission was denied",
            )
        if "timed out" in message or "timeout" in message:
            return ScreenBackendError("timeout", "screen capture timed out")
        return ScreenBackendError(
            "backend_failure",
            "screen capture backend failed",
        )


@dataclass(frozen=True, slots=True)
class RealScreenProvider:
    backend: ScreenBackend = field(default_factory=MacOSScreencaptureBackend)
    device_name: str = "desktop_screen"

    def capture_screen(
        self,
        *,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceResult:
        try:
            screenshot = self.backend.capture_png()
        except Exception as error:
            return self._error_result(error, task_id, metadata)

        return DeviceResult(
            device_name=self.device_name,
            task_id=task_id,
            output={
                "type": "image",
                "bytes": screenshot,
                "mime_type": "image/png",
                "source": "screen",
            },
            metadata={
                "real_device_requested": True,
                **dict(metadata or {}),
            },
        )

    def _error_result(
        self,
        error: Exception,
        task_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> DeviceResult:
        if isinstance(error, ScreenBackendError):
            code = error.code
            message = str(error)
        elif isinstance(error, PermissionError):
            code = "permission_denied"
            message = "screen capture permission was denied"
        elif isinstance(error, TimeoutError):
            code = "timeout"
            message = "screen capture timed out"
        else:
            code = "backend_failure"
            message = "screen capture backend failed"

        return DeviceResult(
            device_name=self.device_name,
            task_id=task_id,
            output=None,
            metadata={"real_device_requested": True, **dict(metadata or {})},
            error=DeviceError(
                device_name=self.device_name,
                message=message,
                code=code,
                metadata={"device_kind": "screen"},
            ),
        )


@dataclass(frozen=True, slots=True)
class MockScreenProvider:
    device_name: str = "mock_screen"
    scene_summary: str = "Mock screen shows an Ella web page."

    def capture_screen(
        self,
        *,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceResult:
        return DeviceResult(
            device_name=self.device_name,
            task_id=task_id,
            output={
                "type": "image",
                "frame": "mock-screen-frame",
                "mime_type": "image/png",
                "source": "screen",
                "scene_summary": self.scene_summary,
            },
            metadata={"mock": True, **dict(metadata or {})},
        )


@dataclass(frozen=True, slots=True)
class UnavailableScreenProvider:
    device_name: str = "unavailable_screen"
    reason: str = "screen capture is unavailable"

    def capture_screen(
        self,
        *,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceResult:
        return DeviceResult(
            device_name=self.device_name,
            task_id=task_id,
            output=None,
            metadata={"real_device_requested": True, **dict(metadata or {})},
            error=DeviceError(
                device_name=self.device_name,
                message=self.reason,
                code="device_unavailable",
                metadata={"device_kind": "screen"},
            ),
        )
