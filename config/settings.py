import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
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
DEEPSEEK_API_KEY_ENV_NAMES = ("DEEPSEEK_API_KEY",)

CONFIG_NAMES = {
    "ELLA_MODEL_PROVIDER": "MODEL_PROVIDER",
    "ELLA_QWEN_API_KEY": "QWEN_API_KEY",
    "ELLA_QWEN_LLM_MODEL": "QWEN_LLM_MODEL",
    "ELLA_QWEN_MULTIMODAL_MODEL": "QWEN_MULTIMODAL_MODEL",
    "ELLA_QWEN_SPEECH_MODEL": "QWEN_SPEECH_MODEL",
    "ELLA_DEEPSEEK_API_KEY": "DEEPSEEK_API_KEY",
    "ELLA_DEEPSEEK_LLM_MODEL": "DEEPSEEK_LLM_MODEL",
    "ELLA_DEEPSEEK_BASE_URL": "DEEPSEEK_BASE_URL",
    "ELLA_DEEPSEEK_BYPASS_PROXY": "DEEPSEEK_BYPASS_PROXY",
    "ELLA_DEEPSEEK_THINKING_ENABLED": "DEEPSEEK_THINKING_ENABLED",
    "ELLA_DEEPSEEK_REASONING_EFFORT": "DEEPSEEK_REASONING_EFFORT",
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
    "ELLA_MEMORY_PATH": "MEMORY_PATH",
    "ELLA_TRACE_DIRECTORY": "TRACE_DIRECTORY",
    "ELLA_PLAN_DIRECTORY": "PLAN_DIRECTORY",
    "ELLA_TASK_CHECKPOINT_DIRECTORY": "TASK_CHECKPOINT_DIRECTORY",
    "ELLA_DISPLAY_DIRECTORY": "DISPLAY_DIRECTORY",
    "ELLA_RAW_MEDIA_DIRECTORY": "RAW_MEDIA_DIRECTORY",
    "ELLA_DOCUMENT_DIRECTORY": "DOCUMENT_DIRECTORY",
}

SAFE_DEFAULTS = {
    "ELLA_MODEL_PROVIDER": "qwen",
    "ELLA_QWEN_API_KEY": None,
    "ELLA_QWEN_LLM_MODEL": None,
    "ELLA_QWEN_MULTIMODAL_MODEL": None,
    "ELLA_QWEN_SPEECH_MODEL": None,
    "ELLA_DEEPSEEK_API_KEY": None,
    "ELLA_DEEPSEEK_LLM_MODEL": "deepseek-v4-pro",
    "ELLA_DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    "ELLA_DEEPSEEK_BYPASS_PROXY": True,
    "ELLA_DEEPSEEK_THINKING_ENABLED": True,
    "ELLA_DEEPSEEK_REASONING_EFFORT": "high",
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
    "ELLA_MEMORY_PATH": user_config.PROJECT_ROOT / "memory" / "memory.md",
    "ELLA_TRACE_DIRECTORY": user_config.PROJECT_ROOT / "trace",
    "ELLA_PLAN_DIRECTORY": user_config.PROJECT_ROOT / "output" / "plans",
    "ELLA_TASK_CHECKPOINT_DIRECTORY": (
        user_config.PROJECT_ROOT / "output" / "tasks"
    ),
    "ELLA_DISPLAY_DIRECTORY": user_config.PROJECT_ROOT / "output" / "display",
    "ELLA_RAW_MEDIA_DIRECTORY": (
        user_config.PROJECT_ROOT / "output" / "raw_media"
    ),
    "ELLA_DOCUMENT_DIRECTORY": (
        user_config.PROJECT_ROOT / "output" / "documents"
    ),
}


@dataclass(frozen=True, slots=True)
class EllaSettings:
    model_provider: str
    qwen_api_key: str | None
    qwen_llm_model: str | None
    qwen_multimodal_model: str | None
    qwen_speech_model: str | None
    deepseek_api_key: str | None
    deepseek_llm_model: str | None
    deepseek_base_url: str
    deepseek_bypass_proxy: bool
    deepseek_thinking_enabled: bool
    deepseek_reasoning_effort: str
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
    memory_path: Path = user_config.PROJECT_ROOT / "memory" / "memory.md"
    trace_directory: Path = user_config.PROJECT_ROOT / "trace"
    plan_directory: Path = user_config.PROJECT_ROOT / "output" / "plans"
    task_checkpoint_directory: Path = (
        user_config.PROJECT_ROOT / "output" / "tasks"
    )
    display_directory: Path = user_config.PROJECT_ROOT / "output" / "display"
    raw_media_directory: Path = (
        user_config.PROJECT_ROOT / "output" / "raw_media"
    )
    document_directory: Path = (
        user_config.PROJECT_ROOT / "output" / "documents"
    )


def load_settings(overrides: Mapping[str, Any] | None = None) -> EllaSettings:
    values = _config_values()
    if overrides is not None:
        values.update(overrides)

    api_key = _optional_string(values, "ELLA_QWEN_API_KEY")
    deepseek_api_key = _optional_string(values, "ELLA_DEEPSEEK_API_KEY")
    if overrides is None:
        api_key = _first_environment_value(QWEN_API_KEY_ENV_NAMES) or api_key
        deepseek_api_key = (
            _first_environment_value(DEEPSEEK_API_KEY_ENV_NAMES)
            or deepseek_api_key
        )

    model_provider = _string(values, "ELLA_MODEL_PROVIDER", "qwen").lower()
    if model_provider not in {"mock", "qwen", "deepseek"}:
        raise ValueError(f"unsupported model provider: {model_provider}")
    reasoning_effort = _string(
        values,
        "ELLA_DEEPSEEK_REASONING_EFFORT",
        "high",
    ).lower()
    if reasoning_effort not in {"low", "high", "max"}:
        raise ValueError(
            "DEEPSEEK_REASONING_EFFORT must be low, high, or max"
        )

    return EllaSettings(
        model_provider=model_provider,
        qwen_api_key=api_key,
        qwen_llm_model=_optional_string(values, "ELLA_QWEN_LLM_MODEL"),
        qwen_multimodal_model=_optional_string(
            values,
            "ELLA_QWEN_MULTIMODAL_MODEL",
        ),
        qwen_speech_model=_optional_string(values, "ELLA_QWEN_SPEECH_MODEL"),
        deepseek_api_key=deepseek_api_key,
        deepseek_llm_model=_optional_string(
            values,
            "ELLA_DEEPSEEK_LLM_MODEL",
        ),
        deepseek_base_url=_string(
            values,
            "ELLA_DEEPSEEK_BASE_URL",
            "https://api.deepseek.com",
        ).rstrip("/"),
        deepseek_bypass_proxy=_boolean(
            values,
            "ELLA_DEEPSEEK_BYPASS_PROXY",
            True,
        ),
        deepseek_thinking_enabled=_boolean(
            values,
            "ELLA_DEEPSEEK_THINKING_ENABLED",
            True,
        ),
        deepseek_reasoning_effort=reasoning_effort,
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
        memory_path=_path(values, "ELLA_MEMORY_PATH"),
        trace_directory=_path(values, "ELLA_TRACE_DIRECTORY"),
        plan_directory=_path(values, "ELLA_PLAN_DIRECTORY"),
        task_checkpoint_directory=_path(
            values,
            "ELLA_TASK_CHECKPOINT_DIRECTORY",
        ),
        display_directory=_path(values, "ELLA_DISPLAY_DIRECTORY"),
        raw_media_directory=_path(values, "ELLA_RAW_MEDIA_DIRECTORY"),
        document_directory=_path(values, "ELLA_DOCUMENT_DIRECTORY"),
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


def _path(values: Mapping[str, Any], name: str) -> Path:
    value = values.get(name)
    if value is None or str(value).strip() == "":
        raise ValueError(f"path value for {name} must not be empty")
    return Path(value).expanduser().resolve()


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
