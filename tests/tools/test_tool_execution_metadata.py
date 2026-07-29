from dataclasses import FrozenInstanceError

import pytest

from tools.base import (
    ToolDefinition,
    ToolIdempotency,
    ToolResult,
    ToolUncertainPolicy,
)
from tools.manager import CapabilityUnavailableError, ToolManager


class MetadataTool:
    name = "metadata_tool"
    allowed_roles = ("main_agent",)

    def __init__(self, definition: ToolDefinition) -> None:
        self.definition = definition

    def run(self, context, arguments=None) -> ToolResult:  # pragma: no cover
        raise AssertionError("metadata resolution must not execute tools")


def definition(**overrides) -> ToolDefinition:
    values = {
        "name": "metadata_tool",
        "description": "Expose metadata for tests.",
        "schema_version": "1.0",
        "input_schema": {"type": "object", "properties": {}},
        "input_examples": (),
        "output_schema": {"type": "object", "properties": {}},
    }
    values.update(overrides)
    return ToolDefinition(**values)


def test_tool_definition_has_safe_backward_compatible_metadata_defaults():
    value = definition()

    assert value.version == "1"
    assert value.idempotency is ToolIdempotency.UNKNOWN
    assert value.side_effecting is False
    assert value.uncertain_policy is ToolUncertainPolicy.NEVER
    assert value.overridable_fields == ()


def test_manager_resolves_authoritative_immutable_metadata():
    manager = ToolManager()
    manager.register(
        MetadataTool(
            definition(
                version="2",
                idempotency=ToolIdempotency.NON_IDEMPOTENT,
                side_effecting=True,
                uncertain_policy=ToolUncertainPolicy.POSSIBLE_AFTER_DISPATCH,
            )
        )
    )

    metadata = manager.resolve_execution_metadata("metadata_tool", "2")

    assert metadata.name == "metadata_tool"
    assert metadata.version == "2"
    assert metadata.side_effecting is True
    assert metadata.idempotency is ToolIdempotency.NON_IDEMPOTENT
    with pytest.raises(FrozenInstanceError):
        metadata.version = "changed"


def test_only_declared_fields_may_be_overridden():
    manager = ToolManager()
    manager.register(
        MetadataTool(
            definition(
                overridable_fields=("idempotency",),
            )
        )
    )

    metadata = manager.resolve_execution_metadata(
        "metadata_tool",
        "1",
        {"idempotency": "idempotent"},
    )
    assert metadata.idempotency is ToolIdempotency.IDEMPOTENT
    assert metadata.overridden_fields == ("idempotency",)

    with pytest.raises(ValueError, match="not allowed"):
        manager.resolve_execution_metadata(
            "metadata_tool", "1", {"side_effecting": True}
        )


def test_missing_or_version_mismatched_tool_is_rejected():
    manager = ToolManager()
    manager.register(MetadataTool(definition(version="2")))

    with pytest.raises(CapabilityUnavailableError, match="not registered"):
        manager.resolve_execution_metadata("missing", "1")
    with pytest.raises(CapabilityUnavailableError, match="version 1"):
        manager.resolve_execution_metadata("metadata_tool", "1")


def test_definition_rejects_unsupported_override_fields():
    with pytest.raises(ValueError, match="unsupported"):
        definition(overridable_fields=("provider_credentials",))


def test_manager_does_not_store_step_runtime_state():
    manager = ToolManager()
    assert not hasattr(manager, "step_tool_availability")
    assert not hasattr(manager, "step_states")
