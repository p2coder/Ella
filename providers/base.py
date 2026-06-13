from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ProviderError:
    provider_name: str
    message: str
    code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "message": self.message,
            "code": self.code,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ProviderResult:
    provider_name: str
    model_name: str
    trace_id: str | None
    output: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    error: ProviderError | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None

    @property
    def failed(self) -> bool:
        return self.error is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "trace_id": self.trace_id,
            "output": self.output,
            "metadata": self.metadata,
            "error": None if self.error is None else self.error.to_dict(),
        }
