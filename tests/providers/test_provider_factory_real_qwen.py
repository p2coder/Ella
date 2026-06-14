from importlib import import_module

from config.settings import load_settings
from providers.factory import ProviderFactory
from providers.mock import MockLLMProvider, MockMultimodalProvider


def real_settings(api_key="sk-real-configured"):
    return load_settings(
        {
            "ELLA_USE_REAL_PROVIDERS": True,
            "ELLA_MODEL_PROVIDER": "qwen",
            "ELLA_QWEN_API_KEY": api_key,
            "ELLA_QWEN_LLM_MODEL": "qwen-plus",
            "ELLA_QWEN_MULTIMODAL_MODEL": "qwen-vl-plus",
        }
    )


def test_factory_wires_default_real_qwen_transports_without_test_callable():
    factory = ProviderFactory(real_settings())
    qwen = import_module("providers.qwen")

    llm = factory.llm()
    multimodal = factory.multimodal()

    assert isinstance(llm, qwen.QwenLLMProvider)
    assert isinstance(llm.client, qwen.DashScopeOpenAITransport)
    assert isinstance(multimodal, qwen.QwenMultimodalProvider)
    assert isinstance(multimodal.client, qwen.DashScopeOpenAITransport)


def test_factory_repr_does_not_expose_api_key():
    factory = ProviderFactory(real_settings(api_key="sk-do-not-log"))

    assert "sk-do-not-log" not in repr(factory)


def test_factory_keeps_default_mode_mock_only():
    factory = ProviderFactory(load_settings({"ELLA_USE_REAL_PROVIDERS": False}))

    assert isinstance(factory.llm(), MockLLMProvider)
    assert isinstance(factory.multimodal(), MockMultimodalProvider)


def test_factory_missing_real_configuration_remains_unavailable():
    factory = ProviderFactory(real_settings(api_key=None))

    result = factory.llm().generate("hello")

    assert result.failed
    assert result.error.code == "provider_unavailable"
