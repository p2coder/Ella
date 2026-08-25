from config.settings import load_settings
from providers.deepseek import DeepSeekLLMProvider, DeepSeekOpenAITransport
from providers.factory import ProviderFactory


def _settings():
    return load_settings(
        {
            "ELLA_USE_REAL_PROVIDERS": True,
            "ELLA_MODEL_PROVIDER": "deepseek",
            "ELLA_DEEPSEEK_API_KEY": "deepseek-secret",
            "ELLA_DEEPSEEK_LLM_MODEL": "deepseek-v4-pro",
            "ELLA_QWEN_API_KEY": "sk-qwen-secret",
            "ELLA_QWEN_MULTIMODAL_MODEL": "qwen-vl-plus",
            "ELLA_QWEN_SPEECH_MODEL": "qwen3-asr-flash",
        }
    )


def test_factory_selects_deepseek_for_text_llm() -> None:
    provider = ProviderFactory(_settings()).llm()

    assert isinstance(provider, DeepSeekLLMProvider)
    assert isinstance(provider.client, DeepSeekOpenAITransport)
    assert provider.model_name == "deepseek-v4-pro"


def test_deepseek_text_selection_keeps_qwen_device_models() -> None:
    factory = ProviderFactory(_settings())

    assert factory.multimodal().provider_name == "qwen_multimodal"
    assert factory.speech().provider_name == "qwen_speech"


def test_factory_does_not_expose_deepseek_key() -> None:
    assert "deepseek-secret" not in repr(ProviderFactory(_settings()))


def test_missing_deepseek_key_returns_provider_unavailable() -> None:
    settings = load_settings(
        {
            "ELLA_USE_REAL_PROVIDERS": True,
            "ELLA_MODEL_PROVIDER": "deepseek",
            "ELLA_DEEPSEEK_API_KEY": None,
            "ELLA_DEEPSEEK_LLM_MODEL": "deepseek-v4-pro",
        }
    )

    result = ProviderFactory(settings).llm().generate("hello")

    assert result.failed
    assert result.error.metadata["missing"] == "DEEPSEEK_API_KEY"
