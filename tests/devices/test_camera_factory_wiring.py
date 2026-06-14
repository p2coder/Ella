from config.settings import load_settings
from devices.camera import MockCameraProvider, RealCameraProvider
from devices.factory import DeviceFactory


def test_factory_returns_mock_camera_when_real_providers_are_disabled():
    factory = DeviceFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": False,
                "ELLA_CAMERA_ENABLED": True,
            }
        )
    )

    assert isinstance(factory.camera(), MockCameraProvider)


def test_factory_returns_real_camera_only_when_both_flags_are_enabled():
    factory = DeviceFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": True,
                "ELLA_CAMERA_ENABLED": True,
                "ELLA_CAMERA_DEVICE": "2",
            }
        )
    )

    camera = factory.camera()

    assert isinstance(camera, RealCameraProvider)
    assert camera.camera_device == "2"


def test_factory_keeps_disabled_camera_unavailable():
    factory = DeviceFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": True,
                "ELLA_CAMERA_ENABLED": False,
            }
        )
    )

    result = factory.camera().capture_frame()

    assert result.failed
    assert result.error.code == "device_unavailable"

