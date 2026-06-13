from dataclasses import dataclass, field
from typing import Any

from devices.camera import CameraProvider, MockCameraProvider
from events.signal import RawSignal
from providers.mock import MockVisionProvider
from providers.vision import VisionProvider


@dataclass(frozen=True, slots=True)
class CameraSourceResult:
    raw_signal: RawSignal | None
    submitted: bool = False
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CameraSource:
    camera_provider: CameraProvider = field(default_factory=MockCameraProvider)
    vision_provider: VisionProvider = field(default_factory=MockVisionProvider)

    def capture_scene_summary(self, *, trace_id: str) -> CameraSourceResult:
        camera_result = self.camera_provider.capture_frame(trace_id=trace_id)
        if camera_result.failed:
            return CameraSourceResult(
                raw_signal=None,
                error=f"camera capture failed: {camera_result.error.message}",
                metadata=self._metadata(),
            )

        vision_result = self.vision_provider.describe(
            camera_result.output,
            trace_id=trace_id,
        )
        if vision_result.failed:
            return CameraSourceResult(
                raw_signal=None,
                error=f"vision summary failed: {vision_result.error.message}",
                metadata=self._metadata(),
            )

        summary = vision_result.output["scene_summary"]
        return CameraSourceResult(
            raw_signal=RawSignal(
                trace_id=trace_id,
                source="camera",
                payload={
                    "type": "image_summary",
                    "summary": summary,
                },
            ),
            metadata=self._metadata(),
        )

    def _metadata(self) -> dict[str, Any]:
        return {
            "camera_provider": self.camera_provider.device_name,
            "vision_provider": self.vision_provider.provider_name,
            "ambient_state_updated": False,
        }
