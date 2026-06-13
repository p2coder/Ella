from typing import Any, Protocol, runtime_checkable

from .base import ProviderResult


@runtime_checkable
class VisionProvider(Protocol):
    provider_name: str
    model_name: str

    def describe(
        self,
        image: Any,
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        ...


@runtime_checkable
class MultimodalProvider(Protocol):
    provider_name: str
    model_name: str

    def describe(
        self,
        inputs: dict[str, Any],
        *,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderResult:
        ...
