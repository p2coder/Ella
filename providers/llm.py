from typing import Any, Protocol, runtime_checkable

from .base import ProviderResult


@runtime_checkable
class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def generate(
        self,
        prompt: str,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        ...
