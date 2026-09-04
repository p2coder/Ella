import importlib

import config.config as user_config
from config.settings import EllaSettings, load_settings


def test_default_settings_are_mock_safe():
    settings = load_settings(
        {
            "ELLA_QWEN_API_KEY": None,
            "ELLA_QWEN_LLM_MODEL": None,
            "ELLA_QWEN_MULTIMODAL_MODEL": None,
            "ELLA_QWEN_SPEECH_MODEL": None,
            "ELLA_USE_REAL_PROVIDERS": False,
            "ELLA_DEBUG_STORE_RAW_MEDIA": False,
            "ELLA_MIC_ENABLED": False,
            "ELLA_CAMERA_ENABLED": False,
            "ELLA_DEEPSEEK_REASONING_EFFORT": "high",
        }
    )

    assert settings.model_provider == "qwen"
    assert settings.qwen_api_key is None
    assert settings.qwen_llm_model is None
    assert settings.qwen_llm_response_format == "json_object"
    assert settings.qwen_llm_enable_thinking is False
    assert settings.qwen_multimodal_model is None
    assert settings.qwen_speech_model is None
    assert settings.deepseek_api_key is None
    assert settings.deepseek_llm_model == "deepseek-v4-pro"
    assert settings.deepseek_thinking_enabled is True
    assert settings.deepseek_bypass_proxy is True
    assert settings.deepseek_reasoning_effort == "high"
    assert settings.use_real_providers is False
    assert settings.debug_store_raw_media is False
    assert settings.mic_enabled is False
    assert settings.camera_enabled is False
    assert settings.mic_device == "default"
    assert settings.camera_device == "default"
    assert settings.mic_always_listening is False
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


def test_tool_result_ttl_overrides_are_validated():
    settings = load_settings(
        {"ELLA_TOOL_RESULT_TTL_OVERRIDES": {"camera_scene": 30, "read": None}}
    )

    assert settings.tool_result_ttl_overrides == {
        "camera_scene": 30.0,
        "read": None,
    }


def test_invalid_tool_result_ttl_override_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="invalid TTL override"):
        load_settings({"ELLA_TOOL_RESULT_TTL_OVERRIDES": {"camera_scene": -1}})


def test_workflow_and_subagent_budgets_can_be_reduced() -> None:
    settings = load_settings(
        {
            "ELLA_WORKFLOW_MAX_PARALLEL_CHILDREN": 2,
            "ELLA_WORKFLOW_MAX_TOTAL_CHILDREN": 4,
            "ELLA_WORKFLOW_MAX_WALL_SECONDS": 60,
            "ELLA_SUBAGENT_MAX_DEPTH": 2,
            "ELLA_SUBAGENT_MAX_ADVANCES": 20,
            "ELLA_SUBAGENT_MAX_TIMEOUT_SECONDS": 120,
        }
    )

    assert settings.workflow_max_parallel_children == 2
    assert settings.workflow_max_total_children == 4
    assert settings.workflow_max_wall_seconds == 60
    assert settings.subagent_max_depth == 2
    assert settings.subagent_max_advances == 20
    assert settings.subagent_max_timeout_seconds == 120


def test_workflow_and_subagent_hard_limits_are_enforced() -> None:
    import pytest

    with pytest.raises(ValueError, match="ELLA_WORKFLOW_MAX_TOTAL_CHILDREN"):
        load_settings({"ELLA_WORKFLOW_MAX_TOTAL_CHILDREN": 33})
    with pytest.raises(ValueError, match="ELLA_SUBAGENT_MAX_DEPTH"):
        load_settings({"ELLA_SUBAGENT_MAX_DEPTH": 5})


def test_missing_qwen_api_key_does_not_crash_settings_loading():
    settings = load_settings({"ELLA_USE_REAL_PROVIDERS": "true"})

    assert settings.use_real_providers is True
    assert settings.qwen_api_key is None


def test_programmatic_overrides_are_applied():
    settings = load_settings(
        {
            "ELLA_MODEL_PROVIDER": "mock",
            "ELLA_QWEN_API_KEY": "secret",
            "ELLA_QWEN_LLM_MODEL": "qwen-llm",
            "ELLA_QWEN_LLM_RESPONSE_FORMAT": None,
            "ELLA_QWEN_LLM_ENABLE_THINKING": True,
            "ELLA_QWEN_MULTIMODAL_MODEL": "qwen-vl",
            "ELLA_QWEN_SPEECH_MODEL": "qwen-asr",
            "ELLA_MIC_DEVICE": "studio-mic",
            "ELLA_CAMERA_DEVICE": "front-camera",
            "ELLA_MIC_ENABLED": False,
            "ELLA_CAMERA_ENABLED": False,
            "ELLA_USE_REAL_PROVIDERS": False,
            "ELLA_DEBUG_STORE_RAW_MEDIA": False,
            "ELLA_DEEPSEEK_REASONING_EFFORT": "high",
        }
    )

    assert settings == EllaSettings(
        model_provider="mock",
        qwen_api_key="secret",
        qwen_llm_model="qwen-llm",
        qwen_llm_response_format=None,
        qwen_llm_enable_thinking=True,
        qwen_multimodal_model="qwen-vl",
        qwen_speech_model="qwen-asr",
        deepseek_api_key=None,
        deepseek_llm_model="deepseek-v4-pro",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_bypass_proxy=True,
        deepseek_thinking_enabled=True,
        deepseek_reasoning_effort="high",
        mic_enabled=False,
        mic_device="studio-mic",
        mic_always_listening=False,
        camera_enabled=False,
        camera_device="front-camera",
        camera_background_interval_seconds=5,
        camera_task_fps=1,
        use_real_providers=False,
        debug_store_raw_media=False,
    )


def test_settings_load_user_config_when_no_overrides(monkeypatch):
    monkeypatch.setattr(user_config, "MODEL_PROVIDER", "mock")
    monkeypatch.setattr(user_config, "CAMERA_TASK_FPS", 3)

    settings = load_settings()

    assert settings.model_provider == "mock"
    assert settings.camera_task_fps == 3


def test_missing_user_config_value_uses_safe_default(monkeypatch):
    monkeypatch.delattr(user_config, "CAMERA_TASK_FPS")

    settings = load_settings()

    assert settings.camera_task_fps == 1


def test_non_secret_environment_variables_are_ignored(monkeypatch):
    monkeypatch.setenv("ELLA_USE_REAL_PROVIDERS", "true")
    monkeypatch.setattr(user_config, "USE_REAL_PROVIDERS", False)

    settings = load_settings()

    assert settings.use_real_providers is False


def test_qwen_api_key_supports_provider_environment_name(monkeypatch):
    monkeypatch.delenv("ELLA_QWEN_API_KEY", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-secret")
    monkeypatch.setattr(user_config, "QWEN_API_KEY", None)

    settings = load_settings()

    assert settings.qwen_api_key == "dashscope-secret"


def test_project_api_key_environment_name_has_priority(monkeypatch):
    monkeypatch.setenv("ELLA_QWEN_API_KEY", "ella-secret")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-secret")

    settings = load_settings()

    assert settings.qwen_api_key == "ella-secret"


def test_deepseek_api_key_uses_provider_environment_name(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    monkeypatch.setattr(user_config, "DEEPSEEK_API_KEY", None)

    settings = load_settings()

    assert settings.deepseek_api_key == "deepseek-secret"


def test_deepseek_runtime_options_are_configurable():
    settings = load_settings(
        {
            "ELLA_MODEL_PROVIDER": "deepseek",
            "ELLA_DEEPSEEK_LLM_MODEL": "deepseek-v4-flash",
            "ELLA_DEEPSEEK_THINKING_ENABLED": False,
            "ELLA_DEEPSEEK_BYPASS_PROXY": False,
            "ELLA_DEEPSEEK_REASONING_EFFORT": "max",
        }
    )

    assert settings.model_provider == "deepseek"
    assert settings.deepseek_llm_model == "deepseek-v4-flash"
    assert settings.deepseek_thinking_enabled is False
    assert settings.deepseek_bypass_proxy is False
    assert settings.deepseek_reasoning_effort == "max"


def test_qwen_llm_output_options_are_configurable():
    settings = load_settings(
        {
            "ELLA_QWEN_LLM_RESPONSE_FORMAT": None,
            "ELLA_QWEN_LLM_ENABLE_THINKING": True,
        }
    )

    assert settings.qwen_llm_response_format is None
    assert settings.qwen_llm_enable_thinking is True


def test_invalid_qwen_response_format_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="QWEN_LLM_RESPONSE_FORMAT"):
        load_settings({"ELLA_QWEN_LLM_RESPONSE_FORMAT": "json_schema"})


def test_importing_config_package_has_no_runtime_side_effect():

    config = importlib.import_module("config")

    assert not hasattr(config, "load_settings")
    assert not hasattr(config, "EllaSettings")
