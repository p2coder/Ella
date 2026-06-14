import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from . import config as user_config


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
MAX_MIC_CAPTURE_DURATION_SECONDS = 5
QWEN_API_KEY_ENV_NAMES = (
    "ELLA_QWEN_API_KEY",
    "DASHSCOPE_API_KEY",
    "QWEN_API_KEY",
)

CONFIG_NAMES = {
    "ELLA_MODEL_PROVIDER": "MODEL_PROVIDER",
    "ELLA_QWEN_API_KEY": "QWEN_API_KEY",
    "ELLA_QWEN_LLM_MODEL": "QWEN_LLM_MODEL",
    "ELLA_QWEN_MULTIMODAL_MODEL": "QWEN_MULTIMODAL_MODEL",
    "ELLA_QWEN_SPEECH_MODEL": "QWEN_SPEECH_MODEL",
    "ELLA_MIC_ENABLED": "MIC_ENABLED",
    "ELLA_MIC_DEVICE": "MIC_DEVICE",
    "ELLA_MIC_ALWAYS_LISTENING": "MIC_ALWAYS_LISTENING",
    "ELLA_MIC_CAPTURE_DURATION_SECONDS": "MIC_CAPTURE_DURATION_SECONDS",
    "ELLA_MIC_SAMPLE_RATE": "MIC_SAMPLE_RATE",
    "ELLA_MIC_CHANNELS": "MIC_CHANNELS",
    "ELLA_CAMERA_ENABLED": "CAMERA_ENABLED",
    "ELLA_CAMERA_DEVICE": "CAMERA_DEVICE",
    "ELLA_CAMERA_BACKGROUND_INTERVAL_SECONDS": (
        "CAMERA_BACKGROUND_INTERVAL_SECONDS"
    ),
    "ELLA_CAMERA_TASK_FPS": "CAMERA_TASK_FPS",
    "ELLA_USE_REAL_PROVIDERS": "USE_REAL_PROVIDERS",
    "ELLA_DEBUG_STORE_RAW_MEDIA": "DEBUG_STORE_RAW_MEDIA",
}

SAFE_DEFAULTS = {
    "ELLA_MODEL_PROVIDER": "qwen",
    "ELLA_QWEN_API_KEY": None,
    "ELLA_QWEN_LLM_MODEL": None,
    "ELLA_QWEN_MULTIMODAL_MODEL": None,
    "ELLA_QWEN_SPEECH_MODEL": None,
    "ELLA_MIC_ENABLED": False,
    "ELLA_MIC_DEVICE": "default",
    "ELLA_MIC_ALWAYS_LISTENING": True,
    "ELLA_MIC_CAPTURE_DURATION_SECONDS": 5,
    "ELLA_MIC_SAMPLE_RATE": 16_000,
    "ELLA_MIC_CHANNELS": 1,
    "ELLA_CAMERA_ENABLED": False,
    "ELLA_CAMERA_DEVICE": "default",
    "ELLA_CAMERA_BACKGROUND_INTERVAL_SECONDS": 5,
    "ELLA_CAMERA_TASK_FPS": 1,
    "ELLA_USE_REAL_PROVIDERS": False,
    "ELLA_DEBUG_STORE_RAW_MEDIA": False,
}


@dataclass(frozen=True, slots=True)
class EllaSettings:
    model_provider: str
    qwen_api_key: str | None
    qwen_llm_model: str | None
    qwen_multimodal_model: str | None
    qwen_speech_model: str | None
    mic_enabled: bool
    mic_device: str
    mic_always_listening: bool
    camera_enabled: bool
    camera_device: str
    camera_background_interval_seconds: int
    camera_task_fps: int
    use_real_providers: bool
    debug_store_raw_media: bool
    mic_capture_duration_seconds: int = 5
    mic_sample_rate: int = 16_000
    mic_channels: int = 1


def load_settings(overrides: Mapping[str, Any] | None = None) -> EllaSettings:
    values = _config_values()
    if overrides is not None:
        values.update(overrides)

    api_key = _optional_string(values, "ELLA_QWEN_API_KEY")
    if overrides is None:
        api_key = _first_environment_value(QWEN_API_KEY_ENV_NAMES) or api_key

    return EllaSettings(
        model_provider=_string(values, "ELLA_MODEL_PROVIDER", "qwen"),
        qwen_api_key=api_key,
        qwen_llm_model=_optional_string(values, "ELLA_QWEN_LLM_MODEL"),
        qwen_multimodal_model=_optional_string(
            values,
            "ELLA_QWEN_MULTIMODAL_MODEL",
        ),
        qwen_speech_model=_optional_string(values, "ELLA_QWEN_SPEECH_MODEL"),
        mic_enabled=_boolean(values, "ELLA_MIC_ENABLED", False),
        mic_device=_string(values, "ELLA_MIC_DEVICE", "default"),
        mic_always_listening=_boolean(
            values,
            "ELLA_MIC_ALWAYS_LISTENING",
            True,
        ),
        camera_enabled=_boolean(values, "ELLA_CAMERA_ENABLED", False),
        camera_device=_string(values, "ELLA_CAMERA_DEVICE", "default"),
        camera_background_interval_seconds=_integer(
            values,
            "ELLA_CAMERA_BACKGROUND_INTERVAL_SECONDS",
            5,
        ),
        camera_task_fps=_integer(values, "ELLA_CAMERA_TASK_FPS", 1),
        use_real_providers=_boolean(values, "ELLA_USE_REAL_PROVIDERS", False),
        debug_store_raw_media=_boolean(
            values,
            "ELLA_DEBUG_STORE_RAW_MEDIA",
            False,
        ),
        mic_capture_duration_seconds=_bounded_positive_integer(
            values,
            "ELLA_MIC_CAPTURE_DURATION_SECONDS",
            5,
            maximum=MAX_MIC_CAPTURE_DURATION_SECONDS,
        ),
        mic_sample_rate=_positive_integer(
            values,
            "ELLA_MIC_SAMPLE_RATE",
            16_000,
        ),
        mic_channels=_positive_integer(
            values,
            "ELLA_MIC_CHANNELS",
            1,
        ),
    )


def _config_values() -> dict[str, Any]:
    return {
        setting_name: getattr(
            user_config,
            config_name,
            SAFE_DEFAULTS[setting_name],
        )
        for setting_name, config_name in CONFIG_NAMES.items()
    }


def _first_environment_value(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def _string(
    env: Mapping[str, Any],
    name: str,
    default: str,
) -> str:
    value = env.get(name)
    if value is None or value == "":
        return default
    return str(value)


def _optional_string(env: Mapping[str, Any], name: str) -> str | None:
    value = env.get(name)
    if value is None or value == "":
        return None
    return str(value)


def _boolean(
    env: Mapping[str, Any],
    name: str,
    default: bool,
) -> bool:
    value = env.get(name)
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"invalid boolean value for {name}: {value}")


def _integer(
    env: Mapping[str, Any],
    name: str,
    default: int,
) -> int:
    value = env.get(name)
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ValueError(f"invalid integer value for {name}: {value}")
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"invalid integer value for {name}: {value}") from error


def _positive_integer(
    values: Mapping[str, Any],
    name: str,
    default: int,
) -> int:
    value = values.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"invalid positive integer value for {name}: {value}")
    parsed = _integer(values, name, default)
    if parsed <= 0:
        raise ValueError(f"invalid positive integer value for {name}: {value}")
    return parsed


def _bounded_positive_integer(
    values: Mapping[str, Any],
    name: str,
    default: int,
    *,
    maximum: int,
) -> int:
    parsed = _positive_integer(values, name, default)
    if parsed > maximum:
        raise ValueError(
            f"{name} must be at most {maximum}, got {parsed}"
        )
    return parsed
