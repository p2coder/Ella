import pytest

from runtime.context_window import (
    ContextTooLargeError,
    estimate_tokens,
    prepare_context,
)


def test_estimate_tokens_uses_prd_character_weights_and_ceiling() -> None:
    assert estimate_tokens("abc") == 1
    assert estimate_tokens("中文") == 2
    assert estimate_tokens("é") == 1
    assert estimate_tokens("a中é") == 2


def test_prepare_context_calls_compression_hook_at_threshold() -> None:
    calls = []

    prepared = prepare_context(
        "a" * 8,
        context_window_tokens=3,
        compression_threshold=0.8,
        compressor=lambda text: calls.append(text) or text,
    )

    assert calls == ["a" * 8]
    assert prepared.compression_requested is True
    assert prepared.estimated_tokens == 3


def test_noop_compression_rejects_only_after_window_is_exceeded() -> None:
    assert prepare_context(
        "a" * 10,
        context_window_tokens=3,
        compression_threshold=0.8,
    ).estimated_tokens == 3
    with pytest.raises(ContextTooLargeError, match="context_too_large"):
        prepare_context(
            "a" * 11,
            context_window_tokens=3,
            compression_threshold=0.8,
        )
