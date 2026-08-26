import sys

from config.settings import load_settings
from providers.base import ProviderError
from providers.mock import (
    MockLLMProvider,
    MockMultimodalProvider,
    MockSpeechProvider,
    MockVisionProvider,
)
from providers.factory import ProviderFactory


def test_factory_returns_mock_providers_by_default():
    factory = ProviderFactory(load_settings({}))

    assert isinstance(factory.llm(), MockLLMProvider)
    assert isinstance(factory.speech(), MockSpeechProvider)
    assert isinstance(factory.vision(), MockVisionProvider)
    assert isinstance(factory.multimodal(), MockMultimodalProvider)


def test_mock_mode_never_imports_real_qwen_provider():
    sys.modules.pop("providers.qwen", None)

    factory = ProviderFactory(load_settings({"ELLA_USE_REAL_PROVIDERS": "false"}))

    result = factory.llm().generate("hello", trace_id="trace-mock")

    assert result.succeeded is True
    assert "providers.qwen" not in sys.modules


def test_real_provider_mode_missing_api_key_returns_structured_unavailable_result():
    factory = ProviderFactory(load_settings({"ELLA_USE_REAL_PROVIDERS": "true"}))

    result = factory.multimodal().describe(
        {"text": "Ella，我要出门了"},
        trace_id="trace-missing-key",
    )

    assert result.failed is True
    assert result.error == ProviderError(
        provider_name="unavailable_multimodal",
        message="real provider is unavailable because API key is missing",
        code="provider_unavailable",
        metadata={"requested_provider": "qwen", "missing": "ELLA_QWEN_API_KEY"},
    )


def test_real_unavailable_factory_provides_all_provider_shapes():
    factory = ProviderFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": "true",
                "ELLA_QWEN_API_KEY": "test-key",
            }
        )
    )

    assert factory.llm().generate("hello").error.code == "provider_unavailable"
    assert factory.speech().transcribe({"audio": "mock"}).error.code == (
        "provider_unavailable"
    )
    assert factory.vision().describe("frame").error.code == "provider_unavailable"
    assert factory.multimodal().describe({"image": "frame"}).error.code == (
        "provider_unavailable"
    )
