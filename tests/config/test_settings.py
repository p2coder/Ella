import importlib

from config.settings import EllaSettings, load_settings


def test_default_settings_are_mock_safe():
    settings = load_settings({})

    assert settings.model_provider == "qwen"
    assert settings.qwen_api_key is None
    assert settings.qwen_llm_model is None
    assert settings.qwen_multimodal_model is None
    assert settings.qwen_speech_model is None
    assert settings.use_real_providers is False
    assert settings.debug_store_raw_media is False
    assert settings.mic_enabled is False
    assert settings.camera_enabled is False
    assert settings.mic_device == "default"
    assert settings.camera_device == "default"
    assert settings.mic_always_listening is True
    assert settings.camera_background_interval_seconds == 5
    assert settings.camera_task_fps == 1


def test_boolean_parsing_accepts_common_values():
    settings = load_settings(
        {
            "ELLA_USE_REAL_PROVIDERS": "true",
            "ELLA_DEBUG_STORE_RAW_MEDIA": "1",
            "ELLA_MIC_ENABLED": "yes",
            "ELLA_MIC_ALWAYS_LISTENING": "on",
            "ELLA_CAMERA_ENABLED": "false",
        }
    )

    assert settings.use_real_providers is True
    assert settings.debug_store_raw_media is True
    assert settings.mic_enabled is True
    assert settings.mic_always_listening is True
    assert settings.camera_enabled is False


def test_numeric_camera_settings_are_parsed():
    settings = load_settings(
        {
            "ELLA_CAMERA_BACKGROUND_INTERVAL_SECONDS": "10",
            "ELLA_CAMERA_TASK_FPS": "2",
        }
    )

    assert settings.camera_background_interval_seconds == 10
    assert settings.camera_task_fps == 2


def test_missing_qwen_api_key_does_not_crash_settings_loading():
    settings = load_settings({"ELLA_USE_REAL_PROVIDERS": "true"})

    assert settings.use_real_providers is True
    assert settings.qwen_api_key is None


def test_environment_overrides_are_applied():
    settings = load_settings(
        {
            "ELLA_MODEL_PROVIDER": "mock",
            "ELLA_QWEN_API_KEY": "secret",
            "ELLA_QWEN_LLM_MODEL": "qwen-llm",
            "ELLA_QWEN_MULTIMODAL_MODEL": "qwen-vl",
            "ELLA_QWEN_SPEECH_MODEL": "qwen-asr",
            "ELLA_MIC_DEVICE": "studio-mic",
            "ELLA_CAMERA_DEVICE": "front-camera",
        }
    )

    assert settings == EllaSettings(
        model_provider="mock",
        qwen_api_key="secret",
        qwen_llm_model="qwen-llm",
        qwen_multimodal_model="qwen-vl",
        qwen_speech_model="qwen-asr",
        mic_enabled=False,
        mic_device="studio-mic",
        mic_always_listening=True,
        camera_enabled=False,
        camera_device="front-camera",
        camera_background_interval_seconds=5,
        camera_task_fps=1,
        use_real_providers=False,
        debug_store_raw_media=False,
    )


def test_importing_config_package_has_no_environment_side_effect(monkeypatch):
    monkeypatch.setenv("ELLA_USE_REAL_PROVIDERS", "true")

    config = importlib.import_module("config")

    assert not hasattr(config, "load_settings")
    assert not hasattr(config, "EllaSettings")
