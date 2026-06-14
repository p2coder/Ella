from dataclasses import dataclass

from config.settings import EllaSettings, load_settings

from .camera import (
    MockCameraProvider,
    RealCameraProvider,
    UnavailableCameraProvider,
)
from .microphone import (
    MockMicrophoneProvider,
    RealMicrophoneProvider,
    UnavailableMicrophoneProvider,
)


@dataclass(frozen=True, slots=True)
class DeviceFactory:
    settings: EllaSettings | None = None

    def __post_init__(self) -> None:
        if self.settings is None:
            object.__setattr__(self, "settings", load_settings())

    def microphone(
        self,
    ) -> (
        MockMicrophoneProvider
        | RealMicrophoneProvider
        | UnavailableMicrophoneProvider
    ):
        if not self.settings.use_real_providers:
            return MockMicrophoneProvider()
        if not self.settings.mic_enabled:
            return UnavailableMicrophoneProvider(
                reason="microphone is disabled by settings",
                enabled_flag="ELLA_MIC_ENABLED",
            )
        return RealMicrophoneProvider(
            microphone_device=self.settings.mic_device,
            duration_seconds=self.settings.mic_capture_duration_seconds,
            sample_rate=self.settings.mic_sample_rate,
            channels=self.settings.mic_channels,
        )

    def camera(
        self,
    ) -> MockCameraProvider | RealCameraProvider | UnavailableCameraProvider:
        if not self.settings.use_real_providers:
            return MockCameraProvider()
        if not self.settings.camera_enabled:
            return UnavailableCameraProvider(
                reason="camera is disabled by settings",
                enabled_flag="ELLA_CAMERA_ENABLED",
            )
        return RealCameraProvider(
            camera_device=self.settings.camera_device,
        )
