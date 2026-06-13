from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.settings import EllaSettings, load_settings

from .base import ProviderError, ProviderResult
from .mock import (
    MockLLMProvider,
    MockMultimodalProvider,
    MockSpeechProvider,
    MockVisionProvider,
)


@dataclass(frozen=True, slots=True)
class ProviderFactory:
    settings: EllaSettings | None = None

    def __post_init__(self) -> None:
        if self.settings is None:
            object.__setattr__(self, "settings", load_settings())

    def llm(self) -> MockLLMProvider | "UnavailableLLMProvider":
        if not self.settings.use_real_providers:
            return MockLLMProvider()
        return UnavailableLLMProvider.from_settings(self.settings)

    def speech(self) -> MockSpeechProvider | "UnavailableSpeechProvider":
        if not self.settings.use_real_providers:
            return MockSpeechProvider()
        return UnavailableSpeechProvider.from_settings(self.settings)

    def vision(self) -> MockVisionProvider | "UnavailableVisionProvider":
        if not self.settings.use_real_providers:
            return MockVisionProvider()
        return UnavailableVisionProvider.from_settings(self.settings)

    def multimodal(
        self,
    ) -> MockMultimodalProvider | "UnavailableMultimodalProvider":
        if not self.settings.use_real_providers:
            return MockMultimodalProvider()
        return UnavailableMultimodalProvider.from_settings(self.settings)


@dataclass(frozen=True, slots=True)
class _UnavailableProviderBase:
    provider_name: str
    model_name: str
    requested_provider: str
    api_key_missing: bool

    @classmethod
    def from_settings(cls, settings: EllaSettings):
        return cls(
            requested_provider=settings.model_provider,
            api_key_missing=settings.qwen_api_key is None,
        )

    def _result(self, *, trace_id: str | None) -> ProviderResult:
        message = "real provider is not wired yet"
        metadata: dict[str, Any] = {"requested_provider": self.requested_provider}
        if self.api_key_missing:
            message = "real provider is unavailable because API key is missing"
            metadata["missing"] = "ELLA_QWEN_API_KEY"

        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=None,
            metadata={"real_provider_requested": True},
            error=ProviderError(
                provider_name=self.provider_name,
                message=message,
                code="provider_unavailable",
                metadata=metadata,
            ),
        )


@dataclass(frozen=True, slots=True)
class UnavailableLLMProvider(_UnavailableProviderBase):
    provider_name: str = "unavailable_llm"
    model_name: str = "unavailable-llm"
    requested_provider: str = "qwen"
    api_key_missing: bool = False

    def generate(
        self,
        prompt: str,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return self._result(trace_id=trace_id)


@dataclass(frozen=True, slots=True)
class UnavailableSpeechProvider(_UnavailableProviderBase):
    provider_name: str = "unavailable_speech"
    model_name: str = "unavailable-speech"
    requested_provider: str = "qwen"
    api_key_missing: bool = False

    def transcribe(
        self,
        audio: Any,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return self._result(trace_id=trace_id)


@dataclass(frozen=True, slots=True)
class UnavailableVisionProvider(_UnavailableProviderBase):
    provider_name: str = "unavailable_vision"
    model_name: str = "unavailable-vision"
    requested_provider: str = "qwen"
    api_key_missing: bool = False

    def describe(
        self,
        image: Any,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return self._result(trace_id=trace_id)


@dataclass(frozen=True, slots=True)
class UnavailableMultimodalProvider(_UnavailableProviderBase):
    provider_name: str = "unavailable_multimodal"
    model_name: str = "unavailable-multimodal"
    requested_provider: str = "qwen"
    api_key_missing: bool = False

    def describe(
        self,
        inputs: dict[str, Any],
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return self._result(trace_id=trace_id)
