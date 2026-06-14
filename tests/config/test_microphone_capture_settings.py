import pytest

import config.config as user_config
from config.settings import MAX_MIC_CAPTURE_DURATION_SECONDS, load_settings


def test_default_microphone_capture_settings_are_bounded_and_speech_safe():
    settings = load_settings({})

    assert settings.mic_capture_duration_seconds == 5
    assert settings.mic_sample_rate == 16_000
    assert settings.mic_channels == 1
    assert settings.mic_capture_duration_seconds <= (
        MAX_MIC_CAPTURE_DURATION_SECONDS
    )


def test_microphone_capture_settings_load_from_user_config(monkeypatch):
    monkeypatch.setattr(user_config, "MIC_CAPTURE_DURATION_SECONDS", 8)
    monkeypatch.setattr(user_config, "MIC_SAMPLE_RATE", 48_000)
    monkeypatch.setattr(user_config, "MIC_CHANNELS", 2)

    settings = load_settings()

    assert settings.mic_capture_duration_seconds == 8
    assert settings.mic_sample_rate == 48_000
    assert settings.mic_channels == 2


def test_microphone_capture_environment_variables_are_ignored(
    monkeypatch,
):
    monkeypatch.setattr(user_config, "MIC_CAPTURE_DURATION_SECONDS", 6)
    monkeypatch.setattr(user_config, "MIC_SAMPLE_RATE", 16_000)
    monkeypatch.setattr(user_config, "MIC_CHANNELS", 1)
    monkeypatch.setenv("ELLA_MIC_CAPTURE_DURATION_SECONDS", "12")
    monkeypatch.setenv("ELLA_MIC_SAMPLE_RATE", "44_100")
    monkeypatch.setenv("ELLA_MIC_CHANNELS", "2")

    settings = load_settings()

    assert settings.mic_capture_duration_seconds == 6
    assert settings.mic_sample_rate == 16_000
    assert settings.mic_channels == 1


@pytest.mark.parametrize("duration", [0, -1, 31])
def test_microphone_capture_duration_must_be_positive_and_bounded(duration):
    with pytest.raises(ValueError, match="MIC_CAPTURE_DURATION_SECONDS"):
        load_settings({"ELLA_MIC_CAPTURE_DURATION_SECONDS": duration})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ELLA_MIC_SAMPLE_RATE", 0),
        ("ELLA_MIC_SAMPLE_RATE", -16_000),
        ("ELLA_MIC_SAMPLE_RATE", 16_000.5),
        ("ELLA_MIC_CHANNELS", 0),
        ("ELLA_MIC_CHANNELS", -1),
        ("ELLA_MIC_CHANNELS", 1.5),
    ],
)
def test_sample_rate_and_channels_must_be_positive_integers(name, value):
    with pytest.raises(ValueError, match=name.removeprefix("ELLA_")):
        load_settings({name: value})


def test_loading_microphone_settings_has_no_device_side_effects(monkeypatch):
    import devices.factory as device_factory

    def fail_if_created(*args, **kwargs):
        raise AssertionError("settings loading must not create a DeviceFactory")

    monkeypatch.setattr(device_factory, "DeviceFactory", fail_if_created)

    settings = load_settings({})

    assert settings.mic_capture_duration_seconds == 5
