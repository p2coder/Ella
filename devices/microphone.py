import importlib
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class DeviceError:
    device_name: str
    message: str
    code: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_name": self.device_name,
            "message": self.message,
            "code": self.code,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class DeviceResult:
    device_name: str
    task_id: str | None
    output: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    error: DeviceError | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None

    @property
    def failed(self) -> bool:
        return self.error is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_name": self.device_name,
            "task_id": self.task_id,
            "output": self.output,
            "metadata": self.metadata,
            "error": None if self.error is None else self.error.to_dict(),
        }


@runtime_checkable
class MicrophoneProvider(Protocol):
    device_name: str

    def capture(
        self,
        *,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceResult:
        ...


class MicrophoneBackendError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class MicrophoneBackend(Protocol):
    def record(
        self,
        *,
        device: int | str | None,
        duration_seconds: int,
        sample_rate: int,
        channels: int,
        timeout_seconds: float,
    ) -> bytes:
        ...

    def release(self) -> None:
        ...


@dataclass(slots=True)
class SoundDeviceMicrophoneBackend:
    _sounddevice: Any = field(default=None, init=False, repr=False)

    def record(
        self,
        *,
        device: int | str | None,
        duration_seconds: int,
        sample_rate: int,
        channels: int,
        timeout_seconds: float,
    ) -> bytes:
        del timeout_seconds
        try:
            self._sounddevice = importlib.import_module("sounddevice")
        except ImportError:
            raise MicrophoneBackendError(
                "backend_unavailable",
                "real microphone provider is not wired yet",
            ) from None

        frame_count = duration_seconds * sample_rate
        try:
            audio = self._sounddevice.rec(
                frame_count,
                samplerate=sample_rate,
                channels=channels,
                dtype="int16",
                device=device,
                blocking=True,
            )
        except PermissionError:
            raise
        except Exception as error:
            raise self._mapped_error(error) from None

        try:
            return audio.tobytes()
        except (AttributeError, TypeError):
            raise MicrophoneBackendError(
                "backend_failure",
                "microphone backend returned invalid audio data",
            ) from None

    def release(self) -> None:
        if self._sounddevice is not None:
            try:
                self._sounddevice.stop(ignore_errors=True)
            except Exception:
                pass

    @staticmethod
    def _mapped_error(error: Exception) -> MicrophoneBackendError:
        message = str(error).lower()
        if "permission" in message or "authorized" in message:
            return MicrophoneBackendError(
                "permission_denied",
                "microphone permission was denied",
            )
        if "busy" in message or "in use" in message:
            return MicrophoneBackendError(
                "device_busy",
                "microphone device is busy",
            )
        if (
            "no default input" in message
            or "invalid device" in message
            or "device unavailable" in message
        ):
            return MicrophoneBackendError(
                "device_not_found",
                "microphone device could not be opened",
            )
        if "timeout" in message or "timed out" in message:
            return MicrophoneBackendError(
                "timeout",
                "microphone capture timed out",
            )
        return MicrophoneBackendError(
            "backend_failure",
            "microphone backend failed",
        )


@dataclass(frozen=True, slots=True)
class RealMicrophoneProvider:
    microphone_device: str | int = "default"
    duration_seconds: int = 5
    sample_rate: int = 16_000
    channels: int = 1
    backend: MicrophoneBackend = field(
        default_factory=SoundDeviceMicrophoneBackend
    )
    device_name: str = "sounddevice_microphone"
    max_duration_seconds: int = 30

    def __post_init__(self) -> None:
        if not 0 < self.duration_seconds <= self.max_duration_seconds:
            raise ValueError(
                "duration_seconds must be positive and no greater than "
                f"{self.max_duration_seconds}"
            )
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.channels <= 0:
            raise ValueError("channels must be positive")

    def capture(
        self,
        *,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceResult:
        try:
            audio_bytes = self.backend.record(
                device=self._resolved_device(),
                duration_seconds=self.duration_seconds,
                sample_rate=self.sample_rate,
                channels=self.channels,
                timeout_seconds=float(self.duration_seconds + 5),
            )
        except Exception as error:
            return self._error_result(error, task_id, metadata)
        finally:
            self.backend.release()

        return DeviceResult(
            device_name=self.device_name,
            task_id=task_id,
            output={
                "type": "audio",
                "bytes": audio_bytes,
                "mime_type": "audio/L16",
                "sample_format": "int16",
                "sample_rate": self.sample_rate,
                "channels": self.channels,
                "duration_seconds": self.duration_seconds,
            },
            metadata={
                **dict(metadata or {}),
                "real_device_requested": True,
                "microphone_device": str(self.microphone_device),
            },
        )

    def _resolved_device(self) -> int | str | None:
        if self.microphone_device == "default":
            return None
        if isinstance(self.microphone_device, int):
            return self.microphone_device
        normalized = self.microphone_device.strip()
        if normalized.isdigit():
            return int(normalized)
        return normalized

    def _error_result(
        self,
        error: Exception,
        task_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> DeviceResult:
        if isinstance(error, MicrophoneBackendError):
            code = error.code
            message = str(error)
        elif isinstance(error, PermissionError):
            code = "permission_denied"
            message = "microphone permission was denied"
        elif isinstance(error, TimeoutError):
            code = "timeout"
            message = "microphone capture timed out"
        else:
            code = "backend_failure"
            message = "microphone backend failed"

        return DeviceResult(
            device_name=self.device_name,
            task_id=task_id,
            output=None,
            metadata={"real_device_requested": True, **dict(metadata or {})},
            error=DeviceError(
                device_name=self.device_name,
                message=message,
                code=code,
                metadata={
                    "device_kind": "microphone",
                    "device_name": str(self.microphone_device),
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class MockMicrophoneProvider:
    device_name: str = "mock_microphone"
    transcript: str = "Ella，我要出门了"

    def capture(
        self,
        *,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceResult:
        return DeviceResult(
            device_name=self.device_name,
            task_id=task_id,
            output={
                "type": "audio",
                "transcript": self.transcript,
            },
            metadata={"mock": True, **dict(metadata or {})},
        )


@dataclass(frozen=True, slots=True)
class UnavailableMicrophoneProvider:
    device_name: str = "unavailable_microphone"
    reason: str = "real microphone provider is not wired yet"
    device_label: str = "default"
    enabled_flag: str | None = None

    def capture(
        self,
        *,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceResult:
        error_metadata = {"device_kind": "microphone"}
        if self.enabled_flag is not None:
            error_metadata["enabled_flag"] = self.enabled_flag
        else:
            error_metadata["device_name"] = self.device_label

        return DeviceResult(
            device_name=self.device_name,
            task_id=task_id,
            output=None,
            metadata={"real_device_requested": True, **dict(metadata or {})},
            error=DeviceError(
                device_name=self.device_name,
                message=self.reason,
                code="device_unavailable",
                metadata=error_metadata,
            ),
        )
