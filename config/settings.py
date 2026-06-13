import os
from dataclasses import dataclass
from collections.abc import Mapping


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


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


def load_settings(env: Mapping[str, str] | None = None) -> EllaSettings:
    values = os.environ if env is None else env
    return EllaSettings(
        model_provider=_string(values, "ELLA_MODEL_PROVIDER", "qwen"),
        qwen_api_key=_optional_string(values, "ELLA_QWEN_API_KEY"),
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
    )


def _string(
    env: Mapping[str, str],
    name: str,
    default: str,
) -> str:
    value = env.get(name)
    if value is None or value == "":
        return default
    return value


def _optional_string(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if value is None or value == "":
        return None
    return value


def _boolean(
    env: Mapping[str, str],
    name: str,
    default: bool,
) -> bool:
    value = env.get(name)
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"invalid boolean value for {name}: {value}")


def _integer(
    env: Mapping[str, str],
    name: str,
    default: int,
) -> int:
    value = env.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"invalid integer value for {name}: {value}") from error
