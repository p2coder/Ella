from pathlib import Path

from config.settings import load_settings
from providers.factory import ProviderFactory
from providers.mock import MockLLMProvider


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_provider_factory_keeps_mock_providers_by_default():
    factory = ProviderFactory(load_settings({}))

    assert isinstance(factory.llm(), MockLLMProvider)


def test_provider_factory_uses_qwen_branch_when_real_config_is_complete():
    factory = ProviderFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": "true",
                "ELLA_MODEL_PROVIDER": "qwen",
                "ELLA_QWEN_API_KEY": "test-key",
                "ELLA_QWEN_LLM_MODEL": "qwen-plus",
                "ELLA_QWEN_SPEECH_MODEL": "qwen-audio",
                "ELLA_QWEN_MULTIMODAL_MODEL": "qwen-vl-plus",
            }
        )
    )

    assert factory.llm().model_name == "qwen-plus"
    assert factory.llm().provider_name == "qwen_llm"
    assert factory.speech().model_name == "qwen-audio"
    assert factory.speech().provider_name == "qwen_speech"
    assert factory.vision().model_name == "qwen-vl-plus"
    assert factory.vision().provider_name == "qwen_multimodal"
    assert factory.multimodal().model_name == "qwen-vl-plus"
    assert factory.multimodal().provider_name == "qwen_multimodal"


def test_provider_factory_missing_api_key_does_not_crash():
    factory = ProviderFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": "true",
                "ELLA_MODEL_PROVIDER": "qwen",
                "ELLA_QWEN_LLM_MODEL": "qwen-plus",
            }
        )
    )

    result = factory.llm().generate("hello", trace_id="trace-factory")

    assert result.failed is True
    assert result.error.code == "provider_unavailable"
    assert result.error.metadata["missing"] == "ELLA_QWEN_API_KEY"
    assert result.error.metadata["requested_provider"] == "qwen"


def test_factory_qwen_branch_does_not_make_network_call_without_client():
    factory = ProviderFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": "true",
                "ELLA_MODEL_PROVIDER": "qwen",
                "ELLA_QWEN_API_KEY": "test-key",
                "ELLA_QWEN_LLM_MODEL": "qwen-plus",
            }
        )
    )

    result = factory.llm().generate("hello")

    assert result.failed is True
    assert result.error.message == "Qwen client is not configured"


def test_agent_runtime_sessions_do_not_import_qwen_directly():
    forbidden = "providers.qwen"
    roots = ("agent", "runtime", "sessions")

    offenders = []
    for root in roots:
        for path in (PROJECT_ROOT / root).glob("**/*.py"):
            if forbidden in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(PROJECT_ROOT).as_posix())

    assert offenders == []
