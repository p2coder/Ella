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
    trace_id: str | None
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
            "trace_id": self.trace_id,
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
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceResult:
        ...


@dataclass(frozen=True, slots=True)
class MockMicrophoneProvider:
    device_name: str = "mock_microphone"
    transcript: str = "Ella，我要出门了"

    def capture(
        self,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceResult:
        return DeviceResult(
            device_name=self.device_name,
            trace_id=trace_id,
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
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceResult:
        error_metadata = {"device_kind": "microphone"}
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
