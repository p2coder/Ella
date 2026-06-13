from dataclasses import dataclass
from typing import Any, Callable

from .base import ProviderError, ProviderResult


QwenClient = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class _QwenProviderBase:
    api_key: str | None
    model_name: str
    client: QwenClient | None = None

    @property
    def provider_name(self) -> str:
        raise NotImplementedError

    def _call(
        self,
        input_payload: dict[str, Any],
        *,
        trace_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> ProviderResult:
        result_metadata = {
            **dict(metadata or {}),
            "real_provider_requested": True,
        }
        if self.api_key is None:
            return ProviderResult(
                provider_name=self.provider_name,
                model_name=self.model_name,
                trace_id=trace_id,
                output=None,
                metadata={"real_provider_requested": True},
                error=ProviderError(
                    provider_name=self.provider_name,
                    message="Qwen API key is missing",
                    code="provider_unavailable",
                    metadata={"missing": "ELLA_QWEN_API_KEY"},
                ),
            )
        if self.client is None:
            return ProviderResult(
                provider_name=self.provider_name,
                model_name=self.model_name,
                trace_id=trace_id,
                output=None,
                metadata={"real_provider_requested": True},
                error=ProviderError(
                    provider_name=self.provider_name,
                    message="Qwen client is not configured",
                    code="provider_unavailable",
                    metadata={"reason": "client_missing"},
                ),
            )

        output = self.client(
            {
                "api_key": self.api_key,
                "model_name": self.model_name,
                "input": input_payload,
                "metadata": dict(metadata or {}),
            }
        )
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=output,
            metadata=result_metadata,
        )


@dataclass(frozen=True, slots=True)
class QwenLLMProvider(_QwenProviderBase):
    provider_name: str = "qwen_llm"

    def generate(
        self,
        prompt: str,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return self._call(
            {"prompt": prompt},
            trace_id=trace_id,
            metadata=metadata,
        )


@dataclass(frozen=True, slots=True)
class QwenSpeechProvider(_QwenProviderBase):
    provider_name: str = "qwen_speech"

    def transcribe(
        self,
        audio: Any,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return self._call(
            {"audio": audio},
            trace_id=trace_id,
            metadata=metadata,
        )


@dataclass(frozen=True, slots=True)
class QwenMultimodalProvider(_QwenProviderBase):
    provider_name: str = "qwen_multimodal"

    def describe(
        self,
        inputs: dict[str, Any],
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        return self._call(
            inputs,
            trace_id=trace_id,
            metadata=metadata,
        )


QwenVisionProvider = QwenMultimodalProvider
