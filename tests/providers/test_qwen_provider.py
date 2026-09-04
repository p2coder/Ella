from providers.base import ProviderError, ProviderResult
from providers.llm import LLMProvider
from providers.qwen import (
    QwenLLMProvider,
    QwenMultimodalProvider,
    QwenSpeechProvider,
)
from providers.speech import SpeechProvider
from providers.vision import MultimodalProvider


def test_qwen_provider_construction_does_not_call_network():
    calls = []

    def client(payload):
        calls.append(payload)
        return {"text": "should not be called during construction"}

    provider = QwenLLMProvider(
        api_key="test-key",
        model_name="qwen-plus",
        client=client,
    )

    assert isinstance(provider, LLMProvider)
    assert provider.provider_name == "qwen_llm"
    assert provider.model_name == "qwen-plus"
    assert calls == []


def test_missing_api_key_returns_structured_llm_error():
    provider = QwenLLMProvider(api_key=None, model_name="qwen-plus")

    result = provider.generate("hello", task_id="task-missing-key")

    assert result == ProviderResult(
        provider_name="qwen_llm",
        model_name="qwen-plus",
        task_id="task-missing-key",
        output=None,
        metadata={"real_provider_requested": True},
        error=ProviderError(
            provider_name="qwen_llm",
            message="Qwen API key is missing",
            code="provider_unavailable",
            metadata={"missing": "ELLA_QWEN_API_KEY"},
        ),
    )


def test_missing_client_returns_structured_error_without_network():
    provider = QwenMultimodalProvider(
        api_key="test-key",
        model_name="qwen-vl-plus",
    )

    result = provider.describe({"text": "look"}, task_id="task-no-client")

    assert result.failed is True
    assert result.error == ProviderError(
        provider_name="qwen_multimodal",
        message="Qwen client is not configured",
        code="provider_unavailable",
        metadata={"reason": "client_missing"},
    )
    assert result.task_id == "task-no-client"


def test_qwen_llm_uses_injected_client_when_explicitly_provided():
    calls = []

    def client(payload):
        calls.append(payload)
        return {"text": "真实调用由注入 client 负责"}

    provider = QwenLLMProvider(
        api_key="test-key",
        model_name="qwen-plus",
        client=client,
    )

    result = provider.generate(
        "Ella，我要出门了",
        task_id="task-qwen",
        metadata={"source": "test"},
    )

    assert result == ProviderResult(
        provider_name="qwen_llm",
        model_name="qwen-plus",
        task_id="task-qwen",
        output={"text": "真实调用由注入 client 负责"},
        metadata={"source": "test", "real_provider_requested": True},
    )
    assert calls == [
        {
            "api_key": "test-key",
            "model_name": "qwen-plus",
            "input": {"prompt": "Ella，我要出门了"},
            "metadata": {"source": "test"},
        }
    ]


def test_qwen_speech_and_multimodal_match_provider_interfaces():
    speech = QwenSpeechProvider(api_key=None, model_name="qwen-audio")
    multimodal = QwenMultimodalProvider(api_key=None, model_name="qwen-vl")

    assert isinstance(speech, SpeechProvider)
    assert isinstance(multimodal, MultimodalProvider)
    assert speech.transcribe({"audio": "bytes"}).error.code == (
        "provider_unavailable"
    )
    assert multimodal.describe({"image": "frame"}).error.code == (
        "provider_unavailable"
    )
