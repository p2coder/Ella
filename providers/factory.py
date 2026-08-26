from __future__ import annotations

from dataclasses import dataclass, field
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
    settings: EllaSettings | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.settings is None:
            object.__setattr__(self, "settings", load_settings())

    def llm(self) -> MockLLMProvider | "UnavailableLLMProvider" | object:
        if not self.settings.use_real_providers:
            return MockLLMProvider()
        if self.settings.model_provider == "qwen" and self._qwen_llm_configured():
            from .qwen import DashScopeOpenAITransport, QwenLLMProvider

            return QwenLLMProvider(
                api_key=self.settings.qwen_api_key,
                model_name=self.settings.qwen_llm_model or "qwen-plus",
                client=DashScopeOpenAITransport(
                    response_format=self.settings.qwen_llm_response_format,
                    enable_thinking=self.settings.qwen_llm_enable_thinking,
                ),
            )
        if (
            self.settings.model_provider == "deepseek"
            and self._deepseek_llm_configured()
        ):
            from .deepseek import DeepSeekLLMProvider, DeepSeekOpenAITransport

            return DeepSeekLLMProvider(
                api_key=self.settings.deepseek_api_key,
                model_name=(
                    self.settings.deepseek_llm_model or "deepseek-v4-pro"
                ),
                client=DeepSeekOpenAITransport(
                    base_url=self.settings.deepseek_base_url,
                    bypass_proxy=self.settings.deepseek_bypass_proxy,
                ),
                thinking_enabled=self.settings.deepseek_thinking_enabled,
                reasoning_effort=self.settings.deepseek_reasoning_effort,
            )
        return UnavailableLLMProvider.from_settings(self.settings)

    def speech(self) -> MockSpeechProvider | "UnavailableSpeechProvider" | object:
        if not self.settings.use_real_providers:
            return MockSpeechProvider()
        if self._qwen_speech_configured():
            from .qwen import DashScopeOpenAITransport, QwenSpeechProvider

            return QwenSpeechProvider(
                api_key=self.settings.qwen_api_key,
                model_name=self.settings.qwen_speech_model or "qwen-audio",
                client=DashScopeOpenAITransport(),
            )
        return UnavailableSpeechProvider.from_settings(self.settings)

    def vision(self) -> MockVisionProvider | "UnavailableVisionProvider" | object:
        if not self.settings.use_real_providers:
            return MockVisionProvider()
        if (
            self._qwen_multimodal_configured()
        ):
            from .qwen import DashScopeOpenAITransport, QwenMultimodalProvider

            return QwenMultimodalProvider(
                api_key=self.settings.qwen_api_key,
                model_name=self.settings.qwen_multimodal_model or "qwen-vl-plus",
                client=DashScopeOpenAITransport(),
            )
        return UnavailableVisionProvider.from_settings(self.settings)

    def multimodal(
        self,
    ) -> MockMultimodalProvider | "UnavailableMultimodalProvider" | object:
        if not self.settings.use_real_providers:
            return MockMultimodalProvider()
        if (
            self._qwen_multimodal_configured()
        ):
            from .qwen import DashScopeOpenAITransport, QwenMultimodalProvider

            return QwenMultimodalProvider(
                api_key=self.settings.qwen_api_key,
                model_name=self.settings.qwen_multimodal_model or "qwen-vl-plus",
                client=DashScopeOpenAITransport(),
            )
        return UnavailableMultimodalProvider.from_settings(self.settings)

    def _qwen_llm_configured(self) -> bool:
        return (
            self.settings.qwen_api_key is not None
            and self.settings.qwen_llm_model is not None
        )

    def _qwen_speech_configured(self) -> bool:
        return (
            self.settings.qwen_api_key is not None
            and self.settings.qwen_speech_model is not None
        )

    def _qwen_multimodal_configured(self) -> bool:
        return (
            self.settings.qwen_api_key is not None
            and self.settings.qwen_multimodal_model is not None
        )

    def _deepseek_llm_configured(self) -> bool:
        return (
            self.settings.deepseek_api_key is not None
            and self.settings.deepseek_llm_model is not None
        )


@dataclass(frozen=True, slots=True)
class _UnavailableProviderBase:
    provider_name: str
    model_name: str
    requested_provider: str
    api_key_missing: bool

    @classmethod
    def from_settings(cls, settings: EllaSettings):
        api_key = (
            settings.deepseek_api_key
            if settings.model_provider == "deepseek"
            else settings.qwen_api_key
        )
        return cls(
            requested_provider=settings.model_provider,
            api_key_missing=api_key is None,
        )

    def _result(self, *, trace_id: str | None) -> ProviderResult:
        message = "real provider is not wired yet"
        metadata: dict[str, Any] = {"requested_provider": self.requested_provider}
        if self.api_key_missing:
            message = "real provider is unavailable because API key is missing"
            metadata["missing"] = (
                "DEEPSEEK_API_KEY"
                if self.requested_provider == "deepseek"
                else "ELLA_QWEN_API_KEY"
            )

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
