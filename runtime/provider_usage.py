from __future__ import annotations

from typing import Any, Mapping

from providers.base import ProviderResult


def record_provider_usage(
    task_local_state: dict[str, Any],
    *,
    boundary: str,
    provider: Any,
    result: ProviderResult | None,
    modality: str = "text",
    success: bool,
) -> None:
    usage = _usage_mapping(result)
    provider_value = result if result is not None else provider
    entry = {
        "boundary": boundary,
        "provider_name": getattr(provider_value, "provider_name", None),
        "model_name": getattr(provider_value, "model_name", None),
        "modality": modality,
        "success": bool(success),
        "prompt_tokens": _integer(usage, "prompt_tokens", "input_tokens"),
        "completion_tokens": _integer(usage, "completion_tokens", "output_tokens"),
        "cached_tokens": _cached_tokens(usage),
        "total_tokens": _integer(usage, "total_tokens"),
    }
    calls = task_local_state.setdefault("provider_usage_calls", [])
    if not isinstance(calls, list):
        calls = []
        task_local_state["provider_usage_calls"] = calls
    calls.append(entry)
    # Keep the checkpoint rollup field as a real aggregate over all calls
    # (summed tokens + cache hit rate). Storing the raw usage of only the
    # latest call here made the field report e.g. prompt_cache_hit_tokens: 0
    # even when earlier calls had thousands of cached tokens.
    task_local_state["provider_usage"] = aggregate_provider_usage(calls) or {}


def aggregate_provider_usage(
    calls: object,
    *,
    modality: str | None = "text",
) -> dict[str, object] | None:
    if not isinstance(calls, (list, tuple)):
        return None
    if modality is None:
        selected = tuple(call for call in calls if isinstance(call, Mapping))
    else:
        selected = tuple(
            call
            for call in calls
            if isinstance(call, Mapping) and call.get("modality", "text") == modality
        )
    if not selected:
        return None
    prompt_values = _available_values(selected, "prompt_tokens")
    completion_values = _available_values(selected, "completion_tokens")
    cached_values = _available_values(selected, "cached_tokens")
    total_values = _available_values(selected, "total_tokens")
    if not (prompt_values or completion_values or cached_values or total_values):
        return None
    prompt = sum(prompt_values)
    completion = sum(completion_values)
    cached = sum(cached_values)
    total = sum(total_values) if total_values else prompt + completion
    return {
        "token_usage": total,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_tokens": cached,
        "cache_hit_rate": round(cached / prompt * 100, 1) if prompt else None,
    }


def merge_provider_usage_calls(
    task_local_state: dict[str, Any],
    calls: object,
) -> None:
    """Merge completed child-boundary calls into one task-level ledger."""
    if not isinstance(calls, (list, tuple)):
        return
    incoming = [dict(call) for call in calls if isinstance(call, Mapping)]
    if not incoming:
        return
    ledger = task_local_state.setdefault("provider_usage_calls", [])
    if not isinstance(ledger, list):
        ledger = []
        task_local_state["provider_usage_calls"] = ledger
    ledger.extend(incoming)
    task_local_state["provider_usage"] = aggregate_provider_usage(ledger) or {}


def nested_provider_usage_calls(
    tool_name: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Return child Provider calls embedded by an agent-composition Tool."""
    if tool_name in {"subagent", "subagent_fork"}:
        calls = payload.get("provider_usage_calls", ())
        return tuple(dict(call) for call in calls if isinstance(call, Mapping))
    if tool_name != "workflow":
        return ()

    nested: list[dict[str, Any]] = []
    for child in payload.get("child_results", ()):
        if not isinstance(child, Mapping):
            continue
        result = child.get("result")
        if not isinstance(result, Mapping):
            continue
        calls = result.get("provider_usage_calls", ())
        nested.extend(dict(call) for call in calls if isinstance(call, Mapping))
    return tuple(nested)


def _usage_mapping(result: ProviderResult | None) -> Mapping[str, Any]:
    if result is None:
        return {}
    usage = result.metadata.get("usage")
    return usage if isinstance(usage, Mapping) else {}


def _integer(usage: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = usage.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _cached_tokens(usage: Mapping[str, Any]) -> int | None:
    # OpenAI-compatible: usage.cached_tokens / prompt_tokens_details.cached_tokens.
    # DeepSeek: usage.prompt_cache_hit_tokens at top level.
    direct = _integer(usage, "cached_tokens", "prompt_cache_hit_tokens")
    details = usage.get("prompt_tokens_details", usage.get("input_tokens_details"))
    if isinstance(details, Mapping):
        nested = _integer(details, "cached_tokens")
        if nested is not None:
            return nested
    return direct


def _available_values(
    calls: tuple[Mapping[str, Any], ...],
    key: str,
) -> tuple[int, ...]:
    return tuple(
        value
        for call in calls
        if isinstance((value := call.get(key)), int) and not isinstance(value, bool)
    )
