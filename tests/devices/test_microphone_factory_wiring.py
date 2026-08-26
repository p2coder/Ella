from config.settings import load_settings
from devices.factory import DeviceFactory
from devices.microphone import MockMicrophoneProvider, RealMicrophoneProvider


def test_factory_returns_mock_microphone_when_real_providers_are_disabled():
    factory = DeviceFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": False,
                "ELLA_MIC_ENABLED": True,
            }
        )
    )

    assert isinstance(factory.microphone(), MockMicrophoneProvider)


def test_factory_wires_real_microphone_with_bounded_settings():
    factory = DeviceFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": True,
                "ELLA_MIC_ENABLED": True,
                "ELLA_MIC_DEVICE": "2",
                "ELLA_MIC_CAPTURE_DURATION_SECONDS": 5,
                "ELLA_MIC_SAMPLE_RATE": 48_000,
                "ELLA_MIC_CHANNELS": 2,
            }
        )
    )

    microphone = factory.microphone()

    assert isinstance(microphone, RealMicrophoneProvider)
    assert microphone.microphone_device == "2"
    assert microphone.duration_seconds == 5
    assert microphone.sample_rate == 48_000
    assert microphone.channels == 2


def test_factory_keeps_disabled_microphone_unavailable():
    factory = DeviceFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": True,
                "ELLA_MIC_ENABLED": False,
            }
        )
    )

    result = factory.microphone().capture()

    assert result.failed
    assert result.error.code == "device_unavailable"
