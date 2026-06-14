from dataclasses import dataclass
from typing import Any

from .base import ProviderError, ProviderResult


def _metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    return {"mock": True, **dict(metadata or {})}


def _missing_input_result(
    *,
    provider_name: str,
    model_name: str,
    trace_id: str | None,
    input_name: str,
) -> ProviderResult:
    return ProviderResult(
        provider_name=provider_name,
        model_name=model_name,
        trace_id=trace_id,
        output=None,
        metadata={"mock": True},
        error=ProviderError(
            provider_name=provider_name,
            message=f"mock {input_name} payload is missing",
            code="missing_input",
            metadata={"input_name": input_name},
        ),
    )


@dataclass(frozen=True, slots=True)
class MockLLMProvider:
    provider_name: str = "mock_llm"
    model_name: str = "mock-llm-v1"

    def generate(
        self,
        prompt: str,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output={
                "text": f"Mock response for: {prompt}",
                "summary": "deterministic mock llm output",
            },
            metadata=_metadata(metadata),
        )


@dataclass(frozen=True, slots=True)
class MockSpeechProvider:
    provider_name: str = "mock_speech"
    model_name: str = "mock-speech-v1"
    default_language: str = "zh"

    def transcribe(
        self,
        audio: Any,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        if audio is None:
            return _missing_input_result(
                provider_name=self.provider_name,
                model_name=self.model_name,
                trace_id=trace_id,
                input_name="audio",
            )

        text = audio.get("transcript") if isinstance(audio, dict) else str(audio)
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output={
                "text": text,
                "language": self.default_language,
            },
            metadata=_metadata(metadata),
        )


@dataclass(frozen=True, slots=True)
class MockVisionProvider:
    provider_name: str = "mock_vision"
    model_name: str = "mock-vision-v1"
    scene_summary: str = "Mock scene contains phone, keys, and wallet."
    visible_items: tuple[str, ...] = ("phone", "keys", "wallet")

    def describe(
        self,
        image: Any,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        if image is None:
            return _missing_input_result(
                provider_name=self.provider_name,
                model_name=self.model_name,
                trace_id=trace_id,
                input_name="image",
            )
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output={
                "scene_summary": self.scene_summary,
                "visible_items": self.visible_items,
            },
            metadata=_metadata(metadata),
        )


@dataclass(frozen=True, slots=True)
class MockMultimodalProvider:
    provider_name: str = "mock_multimodal"
    model_name: str = "mock-multimodal-v1"
    visible_items: tuple[str, ...] = ("phone", "keys", "wallet")

    def describe(
        self,
        inputs: dict[str, Any],
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        if not inputs:
            return ProviderResult(
                provider_name=self.provider_name,
                model_name=self.model_name,
                trace_id=trace_id,
                output=None,
                metadata={"mock": True},
                error=ProviderError(
                    provider_name=self.provider_name,
                    message="mock multimodal input is missing",
                    code="missing_input",
                    metadata={"input_name": "inputs"},
                ),
            )

        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output={
                "scene_summary": (
                    "Mock scene contains " + ", ".join(self.visible_items) + "."
                ),
                "visible_items": self.visible_items,
                "observation_type": "visual_scene_summary",
            },
            metadata=_metadata(metadata),
        )
