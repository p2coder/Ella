from providers.base import ProviderError, ProviderResult
from providers.llm import LLMProvider
from providers.mock import (
    MockLLMProvider,
    MockMultimodalProvider,
    MockSpeechProvider,
    MockVisionProvider,
)
from providers.speech import SpeechProvider
from providers.vision import MultimodalProvider, VisionProvider


def test_mock_llm_returns_deterministic_structured_text():
    provider = MockLLMProvider()

    first = provider.generate("remind me", task_id="task-llm")
    second = provider.generate("remind me", task_id="task-llm")

    assert isinstance(provider, LLMProvider)
    assert first == second
    assert first == ProviderResult(
        provider_name="mock_llm",
        model_name="mock-llm-v1",
        task_id="task-llm",
        output={
            "text": "Mock response for: remind me",
            "summary": "deterministic mock llm output",
        },
        metadata={"mock": True},
    )


def test_mock_speech_returns_transcript_from_payload():
    provider = MockSpeechProvider()

    result = provider.transcribe(
        {"transcript": "Ella，我要出门了"},
        task_id="task-speech",
        metadata={"source": "test"},
    )

    assert isinstance(provider, SpeechProvider)
    assert result.provider_name == "mock_speech"
    assert result.model_name == "mock-speech-v1"
    assert result.task_id == "task-speech"
    assert result.output == {
        "text": "Ella，我要出门了",
        "language": "zh",
    }
    assert result.metadata == {"mock": True, "source": "test"}


def test_mock_speech_supports_string_payload():
    provider = MockSpeechProvider()

    result = provider.transcribe("hello ella")

    assert result.output["text"] == "hello ella"


def test_mock_vision_returns_deterministic_scene_summary():
    provider = MockVisionProvider(
        scene_summary="Desk with phone, keys, wallet, and no umbrella."
    )

    result = provider.describe("frame-1", task_id="task-vision")

    assert isinstance(provider, VisionProvider)
    assert result == ProviderResult(
        provider_name="mock_vision",
        model_name="mock-vision-v1",
        task_id="task-vision",
        output={
            "scene_summary": "Desk with phone, keys, wallet, and no umbrella.",
            "visible_items": ("phone", "keys", "wallet"),
        },
        metadata={"mock": True},
    )


def test_mock_multimodal_returns_general_visual_observation():
    provider = MockMultimodalProvider(
        visible_items=("phone", "keys", "wallet", "umbrella"),
    )

    result = provider.describe(
        {"text": "看看我带没带伞", "image": "frame"},
        task_id="task-mm",
    )

    assert isinstance(provider, MultimodalProvider)
    assert result.provider_name == "mock_multimodal"
    assert result.model_name == "mock-multimodal-v1"
    assert result.output == {
        "scene_summary": "Mock scene contains phone, keys, wallet, umbrella.",
        "visible_items": ("phone", "keys", "wallet", "umbrella"),
        "observation_type": "visual_scene_summary",
    }
    assert result.metadata == {"mock": True}


def test_mock_multimodal_does_not_add_task_specific_visibility_fields():
    provider = MockMultimodalProvider(visible_items=("phone", "keys", "wallet"))

    result = provider.describe({"text": "umbrella?", "image": "frame"})

    assert "umbrella_visible" not in result.output
    assert result.output["visible_items"] == ("phone", "keys", "wallet")


def test_mock_provider_errors_are_structured_when_required_input_is_missing():
    speech = MockSpeechProvider()
    multimodal = MockMultimodalProvider()

    speech_result = speech.transcribe(None, task_id="task-missing-audio")
    multimodal_result = multimodal.describe({}, task_id="task-missing-mm")

    assert speech_result.error == ProviderError(
        provider_name="mock_speech",
        message="mock audio payload is missing",
        code="missing_input",
        metadata={"input_name": "audio"},
    )
    assert speech_result.failed is True
    assert multimodal_result.error == ProviderError(
        provider_name="mock_multimodal",
        message="mock multimodal input is missing",
        code="missing_input",
        metadata={"input_name": "inputs"},
    )
    assert multimodal_result.failed is True
