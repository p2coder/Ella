from providers.base import ProviderError, ProviderResult
from providers.llm import LLMProvider
from providers.speech import SpeechProvider
from providers.vision import MultimodalProvider, VisionProvider


class StubLLMProvider:
    provider_name = "stub"
    model_name = "stub-llm"

    def generate(self, prompt, *, trace_id=None, metadata=None):
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output={"text": prompt},
            metadata=dict(metadata or {}),
        )


class StubSpeechProvider:
    provider_name = "stub"
    model_name = "stub-speech"

    def transcribe(self, audio, *, trace_id=None, metadata=None):
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output={"text": "Ella"},
            metadata={"audio": audio, **dict(metadata or {})},
        )


class StubVisionProvider:
    provider_name = "stub"
    model_name = "stub-vision"

    def describe(self, image, *, trace_id=None, metadata=None):
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output={"summary": "A desk scene."},
            metadata={"image": image, **dict(metadata or {})},
        )


class StubMultimodalProvider:
    provider_name = "stub"
    model_name = "stub-multimodal"

    def describe(self, inputs, *, trace_id=None, metadata=None):
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output={"summary": inputs["text"]},
            metadata=dict(metadata or {}),
        )


def test_provider_result_construction_and_serialization():
    result = ProviderResult(
        provider_name="stub",
        model_name="stub-model",
        trace_id="trace-provider",
        output={"answer": "ok"},
        metadata={"latency_ms": 1},
    )

    assert result.succeeded is True
    assert result.failed is False
    assert result.to_dict() == {
        "provider_name": "stub",
        "model_name": "stub-model",
        "trace_id": "trace-provider",
        "output": {"answer": "ok"},
        "metadata": {"latency_ms": 1},
        "error": None,
    }


def test_provider_error_construction_and_structured_result():
    error = ProviderError(
        provider_name="stub",
        message="model unavailable",
        code="provider_unavailable",
        metadata={"retryable": False},
    )
    result = ProviderResult(
        provider_name="stub",
        model_name="stub-model",
        trace_id="trace-error",
        output=None,
        metadata={},
        error=error,
    )

    assert result.succeeded is False
    assert result.failed is True
    assert result.error is error
    assert error.to_dict() == {
        "provider_name": "stub",
        "message": "model unavailable",
        "code": "provider_unavailable",
        "metadata": {"retryable": False},
    }
    assert result.to_dict()["error"] == error.to_dict()


def test_llm_provider_interface_shape():
    provider = StubLLMProvider()

    assert isinstance(provider, LLMProvider)
    result = provider.generate(
        "hello",
        trace_id="trace-llm",
        metadata={"purpose": "test"},
    )

    assert result.provider_name == "stub"
    assert result.model_name == "stub-llm"
    assert result.trace_id == "trace-llm"
    assert result.output == {"text": "hello"}
    assert result.metadata == {"purpose": "test"}


def test_speech_provider_interface_shape():
    provider = StubSpeechProvider()

    assert isinstance(provider, SpeechProvider)
    result = provider.transcribe(b"audio", trace_id="trace-speech")

    assert result.model_name == "stub-speech"
    assert result.output == {"text": "Ella"}
    assert result.metadata["audio"] == b"audio"


def test_vision_and_multimodal_provider_interface_shapes():
    vision = StubVisionProvider()
    multimodal = StubMultimodalProvider()

    assert isinstance(vision, VisionProvider)
    assert isinstance(multimodal, MultimodalProvider)
    assert vision.describe("frame", trace_id="trace-vision").output == {
        "summary": "A desk scene."
    }
    assert multimodal.describe(
        {"text": "look for umbrella", "image": "frame"},
        trace_id="trace-mm",
    ).output == {"summary": "look for umbrella"}
