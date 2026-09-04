import math
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
    "ELLA_QWEN_LLM_RESPONSE_FORMAT": "QWEN_LLM_RESPONSE_FORMAT",
    "ELLA_QWEN_LLM_ENABLE_THINKING": "QWEN_LLM_ENABLE_THINKING",
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
    "ELLA_TASK_CHECKPOINT_DIRECTORY": "TASK_CHECKPOINT_DIRECTORY",
    "ELLA_DISPLAY_DIRECTORY": "DISPLAY_DIRECTORY",
    "ELLA_RAW_MEDIA_DIRECTORY": "RAW_MEDIA_DIRECTORY",
    "ELLA_DOCUMENT_DIRECTORY": "DOCUMENT_DIRECTORY",
    "ELLA_CONTEXT_WINDOW_TOKENS": "CONTEXT_WINDOW_TOKENS",
    "ELLA_CONTEXT_COMPRESSION_THRESHOLD": "CONTEXT_COMPRESSION_THRESHOLD",
    "ELLA_TOOL_RESULT_TTL_OVERRIDES": "TOOL_RESULT_TTL_OVERRIDES",
    "ELLA_WORKFLOW_MAX_SCRIPT_BYTES": "WORKFLOW_MAX_SCRIPT_BYTES",
    "ELLA_WORKFLOW_MAX_WALL_SECONDS": "WORKFLOW_MAX_WALL_SECONDS",
    "ELLA_WORKFLOW_MAX_PARALLEL_CHILDREN": "WORKFLOW_MAX_PARALLEL_CHILDREN",
    "ELLA_WORKFLOW_MAX_TOTAL_CHILDREN": "WORKFLOW_MAX_TOTAL_CHILDREN",
    "ELLA_WORKFLOW_MEMORY_LIMIT_BYTES": "WORKFLOW_MEMORY_LIMIT_BYTES",
    "ELLA_WORKFLOW_MAX_RETURN_BYTES": "WORKFLOW_MAX_RETURN_BYTES",
    "ELLA_SUBAGENT_MAX_DEPTH": "SUBAGENT_MAX_DEPTH",
    "ELLA_SUBAGENT_MAX_ADVANCES": "SUBAGENT_MAX_ADVANCES",
    "ELLA_SUBAGENT_MAX_TIMEOUT_SECONDS": "SUBAGENT_MAX_TIMEOUT_SECONDS",
}

SAFE_DEFAULTS = {
    "ELLA_MODEL_PROVIDER": "qwen",
    "ELLA_QWEN_API_KEY": None,
    "ELLA_QWEN_LLM_MODEL": None,
    "ELLA_QWEN_LLM_RESPONSE_FORMAT": "json_object",
    "ELLA_QWEN_LLM_ENABLE_THINKING": False,
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
    "ELLA_CONTEXT_WINDOW_TOKENS": 1_000_000,
    "ELLA_CONTEXT_COMPRESSION_THRESHOLD": 0.8,
    "ELLA_TOOL_RESULT_TTL_OVERRIDES": {},
    "ELLA_WORKFLOW_MAX_SCRIPT_BYTES": 64 * 1024,
    "ELLA_WORKFLOW_MAX_WALL_SECONDS": 600,
    "ELLA_WORKFLOW_MAX_PARALLEL_CHILDREN": 8,
    "ELLA_WORKFLOW_MAX_TOTAL_CHILDREN": 32,
    "ELLA_WORKFLOW_MEMORY_LIMIT_BYTES": 64 * 1024 * 1024,
    "ELLA_WORKFLOW_MAX_RETURN_BYTES": 1024 * 1024,
    "ELLA_SUBAGENT_MAX_DEPTH": 4,
    "ELLA_SUBAGENT_MAX_ADVANCES": 50,
    "ELLA_SUBAGENT_MAX_TIMEOUT_SECONDS": 300,
}


@dataclass(frozen=True, slots=True)
class EllaSettings:
    model_provider: str
    qwen_api_key: str | None
    qwen_llm_model: str | None
    qwen_llm_response_format: str | None
    qwen_llm_enable_thinking: bool
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
    context_window_tokens: int = 1_000_000
    context_compression_threshold: float = 0.8
    tool_result_ttl_overrides: Mapping[str, float | None] | None = None
    workflow_max_script_bytes: int = 64 * 1024
    workflow_max_wall_seconds: int = 600
    workflow_max_parallel_children: int = 8
    workflow_max_total_children: int = 32
    workflow_memory_limit_bytes: int = 64 * 1024 * 1024
    workflow_max_return_bytes: int = 1024 * 1024
    subagent_max_depth: int = 4
    subagent_max_advances: int = 50
    subagent_max_timeout_seconds: int = 300

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tool_result_ttl_overrides",
            dict(self.tool_result_ttl_overrides or {}),
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
    qwen_response_format = _optional_string(
        values,
        "ELLA_QWEN_LLM_RESPONSE_FORMAT",
    )
    if qwen_response_format not in {None, "json_object"}:
        raise ValueError(
            "QWEN_LLM_RESPONSE_FORMAT must be json_object or None"
        )

    return EllaSettings(
        model_provider=model_provider,
        qwen_api_key=api_key,
        qwen_llm_model=_optional_string(values, "ELLA_QWEN_LLM_MODEL"),
        qwen_llm_response_format=qwen_response_format,
        qwen_llm_enable_thinking=_boolean(
            values,
            "ELLA_QWEN_LLM_ENABLE_THINKING",
            False,
        ),
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
        task_checkpoint_directory=_path(
            values,
            "ELLA_TASK_CHECKPOINT_DIRECTORY",
        ),
        display_directory=_path(values, "ELLA_DISPLAY_DIRECTORY"),
        raw_media_directory=_path(values, "ELLA_RAW_MEDIA_DIRECTORY"),
        document_directory=_path(values, "ELLA_DOCUMENT_DIRECTORY"),
        context_window_tokens=_positive_integer(
            values, "ELLA_CONTEXT_WINDOW_TOKENS", 1_000_000
        ),
        context_compression_threshold=_bounded_ratio(
            values, "ELLA_CONTEXT_COMPRESSION_THRESHOLD", 0.8
        ),
        tool_result_ttl_overrides=_ttl_overrides(
            values,
            "ELLA_TOOL_RESULT_TTL_OVERRIDES",
        ),
        workflow_max_script_bytes=_bounded_positive_integer(
            values, "ELLA_WORKFLOW_MAX_SCRIPT_BYTES", 64 * 1024, maximum=64 * 1024
        ),
        workflow_max_wall_seconds=_bounded_positive_integer(
            values, "ELLA_WORKFLOW_MAX_WALL_SECONDS", 600, maximum=600
        ),
        workflow_max_parallel_children=_bounded_positive_integer(
            values, "ELLA_WORKFLOW_MAX_PARALLEL_CHILDREN", 8, maximum=8
        ),
        workflow_max_total_children=_bounded_positive_integer(
            values, "ELLA_WORKFLOW_MAX_TOTAL_CHILDREN", 32, maximum=32
        ),
        workflow_memory_limit_bytes=_bounded_positive_integer(
            values,
            "ELLA_WORKFLOW_MEMORY_LIMIT_BYTES",
            64 * 1024 * 1024,
            maximum=64 * 1024 * 1024,
        ),
        workflow_max_return_bytes=_bounded_positive_integer(
            values,
            "ELLA_WORKFLOW_MAX_RETURN_BYTES",
            1024 * 1024,
            maximum=1024 * 1024,
        ),
        subagent_max_depth=_bounded_positive_integer(
            values, "ELLA_SUBAGENT_MAX_DEPTH", 4, maximum=4
        ),
        subagent_max_advances=_bounded_positive_integer(
            values, "ELLA_SUBAGENT_MAX_ADVANCES", 50, maximum=50
        ),
        subagent_max_timeout_seconds=_bounded_positive_integer(
            values, "ELLA_SUBAGENT_MAX_TIMEOUT_SECONDS", 300, maximum=300
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


def _bounded_ratio(values: Mapping[str, Any], name: str, default: float) -> float:
    value = float(values.get(name, default))
    if not 0 < value < 1:
        raise ValueError(f"{name.removeprefix('ELLA_')} must be in (0, 1)")
    return value


def _ttl_overrides(
    values: Mapping[str, Any],
    name: str,
) -> dict[str, float | None]:
    raw = values.get(name, {})
    if not isinstance(raw, Mapping):
        raise ValueError(f"{name} must be a mapping")
    result: dict[str, float | None] = {}
    for tool_name, ttl in raw.items():
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError(f"{name} keys must be non-empty tool names")
        if ttl is None:
            result[tool_name] = None
            continue
        if (
            isinstance(ttl, bool)
            or not isinstance(ttl, (int, float))
            or not math.isfinite(ttl)
            or ttl < 0
        ):
            raise ValueError(f"invalid TTL override for {tool_name}: {ttl}")
        result[tool_name] = float(ttl)
    return result


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
