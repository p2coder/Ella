import devices

from config.settings import load_settings
from devices.camera import CameraProvider, MockCameraProvider
from devices.factory import DeviceFactory
from devices.microphone import MicrophoneProvider, MockMicrophoneProvider


def test_factory_returns_mock_devices_by_default():
    factory = DeviceFactory(load_settings({}))

    microphone = factory.microphone()
    camera = factory.camera()

    assert isinstance(microphone, MockMicrophoneProvider)
    assert isinstance(microphone, MicrophoneProvider)
    assert isinstance(camera, MockCameraProvider)
    assert isinstance(camera, CameraProvider)


def test_real_providers_false_never_creates_real_devices_even_when_enabled():
    factory = DeviceFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": "false",
                "ELLA_MIC_ENABLED": "true",
                "ELLA_CAMERA_ENABLED": "true",
            }
        )
    )

    assert factory.microphone().capture().metadata == {"mock": True}
    assert factory.camera().capture_frame().metadata == {"mock": True}


def test_mic_disabled_prevents_real_microphone_provider_creation():
    factory = DeviceFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": "true",
                "ELLA_MIC_ENABLED": "false",
            }
        )
    )

    result = factory.microphone().capture(trace_id="trace-mic-disabled")

    assert result.failed is True
    assert result.error.code == "device_unavailable"
    assert result.error.message == "microphone is disabled by settings"
    assert result.error.metadata == {
        "device_kind": "microphone",
        "enabled_flag": "ELLA_MIC_ENABLED",
    }
    assert result.trace_id == "trace-mic-disabled"


def test_camera_disabled_prevents_real_camera_provider_creation():
    factory = DeviceFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": "true",
                "ELLA_CAMERA_ENABLED": "false",
            }
        )
    )

    result = factory.camera().capture_frame(trace_id="trace-camera-disabled")

    assert result.failed is True
    assert result.error.code == "device_unavailable"
    assert result.error.message == "camera is disabled by settings"
    assert result.error.metadata == {
        "device_kind": "camera",
        "enabled_flag": "ELLA_CAMERA_ENABLED",
    }
    assert result.trace_id == "trace-camera-disabled"


def test_package_import_has_no_device_access_or_factory_side_effects():
    assert not hasattr(devices, "DeviceFactory")
    assert not hasattr(devices, "MockMicrophoneProvider")
    assert not hasattr(devices, "MockCameraProvider")
