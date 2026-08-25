from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .base import ProviderError, ProviderResult


DeepSeekClientFactory = Callable[..., Any]


class DeepSeekTransportError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class DeepSeekOpenAITransport:
    base_url: str = "https://api.deepseek.com"
    timeout_seconds: float = 60.0
    client_factory: DeepSeekClientFactory | None = field(
        default=None,
        repr=False,
    )

    def __call__(self, payload: dict[str, Any]) -> Any:
        factory = self.client_factory or self._openai_factory()
        try:
            client = factory(
                api_key=payload["api_key"],
                base_url=self.base_url,
                timeout=self.timeout_seconds,
            )
            return client.chat.completions.create(
                model=payload["model_name"],
                messages=[{"role": "user", "content": payload["prompt"]}],
                stream=False,
                reasoning_effort=payload["reasoning_effort"],
                extra_body={
                    "thinking": {
                        "type": (
                            "enabled"
                            if payload["thinking_enabled"]
                            else "disabled"
                        )
                    }
                },
            )
        except DeepSeekTransportError:
            raise
        except Exception as error:
            status_code = getattr(error, "status_code", None)
            if status_code in (401, 403):
                raise DeepSeekTransportError(
                    "authentication_error",
                    "DeepSeek rejected authentication",
                ) from None
            if status_code == 429:
                raise DeepSeekTransportError(
                    "rate_limit_error",
                    "DeepSeek rate limit was exceeded",
                ) from None
            if status_code is not None:
                raise DeepSeekTransportError(
                    "provider_error",
                    "DeepSeek returned a service error",
                ) from None
            if isinstance(error, (TimeoutError, ConnectionError)):
                raise DeepSeekTransportError(
                    "timeout_error",
                    "DeepSeek request timed out",
                ) from None
            raise DeepSeekTransportError(
                "transport_error",
                "DeepSeek request transport failed",
            ) from None

    @staticmethod
    def _openai_factory() -> DeepSeekClientFactory:
        try:
            from openai import OpenAI
        except ImportError:
            raise DeepSeekTransportError(
                "provider_unavailable",
                "DeepSeek requires the openai package",
            ) from None
        return OpenAI


@dataclass(frozen=True, slots=True)
class DeepSeekLLMProvider:
    api_key: str | None = field(repr=False)
    model_name: str = "deepseek-v4-pro"
    client: Callable[[dict[str, Any]], Any] | None = field(
        default=None,
        repr=False,
    )
    thinking_enabled: bool = True
    reasoning_effort: str = "high"
    provider_name: str = "deepseek_llm"

    def generate(
        self,
        prompt: str,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        if self.api_key is None:
            return self._error(
                trace_id,
                "provider_unavailable",
                "DeepSeek API key is missing",
                {"missing": "DEEPSEEK_API_KEY"},
            )
        if self.client is None:
            return self._error(
                trace_id,
                "provider_unavailable",
                "DeepSeek client is not configured",
                {"reason": "client_missing"},
            )
        try:
            response = self.client(
                {
                    "api_key": self.api_key,
                    "model_name": self.model_name,
                    "prompt": prompt,
                    "thinking_enabled": self.thinking_enabled,
                    "reasoning_effort": self.reasoning_effort,
                }
            )
            content = self._content(response)
        except DeepSeekTransportError as error:
            return self._error(trace_id, error.code, str(error), {})
        except Exception:
            return self._error(
                trace_id,
                "transport_error",
                "DeepSeek client transport failed",
                {},
            )
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output={"text": content},
            metadata={
                **dict(metadata or {}),
                "real_provider_requested": True,
                "thinking_enabled": self.thinking_enabled,
                "reasoning_effort": self.reasoning_effort,
            },
        )

    @staticmethod
    def _content(response: Any) -> str:
        if isinstance(response, dict):
            try:
                content = response["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                content = None
        else:
            try:
                content = response.choices[0].message.content
            except (AttributeError, IndexError, TypeError):
                content = None
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekTransportError(
                "malformed_response",
                "DeepSeek response did not contain message content",
            )
        return content.strip()

    def _error(
        self,
        trace_id: str | None,
        code: str,
        message: str,
        metadata: dict[str, Any],
    ) -> ProviderResult:
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=None,
            metadata={"real_provider_requested": True},
            error=ProviderError(
                provider_name=self.provider_name,
                message=message,
                code=code,
                metadata=metadata,
            ),
        )
