from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from tools.base import ToolDefinition

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


_FORBIDDEN_TOOL_METADATA_FRAGMENTS = (
    "credential",
    "api_key",
    "authorization",
    "local_path",
    "class_name",
    "debug",
    "raw_media",
    "permission",
)


def serialize_tool_definition(definition: "ToolDefinition") -> dict[str, Any]:
    return {
        "name": definition.name,
        "description": definition.description,
        "input_schema": _sanitize_schema(definition.input_schema),
        "input_examples": definition.input_examples,
        "output_schema": _sanitize_schema(definition.output_schema),
    }


def serialize_tool_definitions(
    definitions: tuple["ToolDefinition", ...],
) -> tuple[dict[str, Any], ...]:
    return tuple(serialize_tool_definition(definition) for definition in definitions)


def _sanitize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in schema.items():
        if _is_forbidden_key(key):
            continue
        if key == "properties" and isinstance(value, dict):
            properties = {
                property_name: _sanitize_schema(property_schema)
                for property_name, property_schema in value.items()
                if not _is_forbidden_key(property_name)
                and isinstance(property_schema, dict)
            }
            sanitized[key] = properties
            continue
        if key == "required" and isinstance(value, (list, tuple)):
            sanitized[key] = [
                item for item in value if isinstance(item, str) and not _is_forbidden_key(item)
            ]
            continue
        if key == "items" and isinstance(value, dict):
            sanitized[key] = _sanitize_schema(value)
            continue
        sanitized[key] = value
    return sanitized


def _is_forbidden_key(key: str) -> bool:
    normalized = key.lower()
    return any(fragment in normalized for fragment in _FORBIDDEN_TOOL_METADATA_FRAGMENTS)
