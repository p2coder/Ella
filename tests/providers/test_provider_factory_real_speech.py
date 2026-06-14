from importlib import import_module

from config.settings import load_settings
from providers.factory import ProviderFactory
from providers.mock import MockSpeechProvider


def test_factory_wires_real_qwen_speech_transport_when_configured():
    factory = ProviderFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": True,
                "ELLA_MODEL_PROVIDER": "qwen",
                "ELLA_QWEN_API_KEY": "sk-configured",
                "ELLA_QWEN_SPEECH_MODEL": "qwen3-asr-flash",
            }
        )
    )
    qwen = import_module("providers.qwen")

    speech = factory.speech()

    assert isinstance(speech, qwen.QwenSpeechProvider)
    assert isinstance(speech.client, qwen.DashScopeOpenAITransport)
    assert speech.model_name == "qwen3-asr-flash"


def test_factory_keeps_speech_mock_only_by_default():
    factory = ProviderFactory(load_settings({"ELLA_USE_REAL_PROVIDERS": False}))

    assert isinstance(factory.speech(), MockSpeechProvider)


def test_factory_missing_speech_configuration_remains_unavailable():
    factory = ProviderFactory(
        load_settings(
            {
                "ELLA_USE_REAL_PROVIDERS": True,
                "ELLA_MODEL_PROVIDER": "qwen",
                "ELLA_QWEN_API_KEY": "sk-configured",
                "ELLA_QWEN_SPEECH_MODEL": None,
            }
        )
    )

    result = factory.speech().transcribe({"bytes": b"audio"})

    assert result.failed
    assert result.error.code == "provider_unavailable"

