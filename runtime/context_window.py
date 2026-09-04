from dataclasses import dataclass
from math import ceil
from typing import Callable


DEFAULT_CONTEXT_WINDOW_TOKENS = 1_000_000
DEFAULT_COMPRESSION_THRESHOLD = 0.8


class ContextTooLargeError(RuntimeError):
    code = "context_too_large"


@dataclass(frozen=True, slots=True)
class PreparedContext:
    text: str
    estimated_tokens: int
    compression_requested: bool


def estimate_tokens(text: str) -> int:
    """Estimate tokens using the deliberately coarse PRD character weights."""
    estimate = 0.0
    for character in text:
        codepoint = ord(character)
        if codepoint <= 0x7F:
            estimate += 0.3
        elif _is_chinese(codepoint):
            estimate += 0.6
        else:
            estimate += 1.0
    return ceil(estimate)


def compress_context(text: str) -> str:
    """Reserved generic compression hook; intentionally a no-op for now."""
    return text


def prepare_context(
    text: str,
    *,
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS,
    compression_threshold: float = DEFAULT_COMPRESSION_THRESHOLD,
    compressor: Callable[[str], str] = compress_context,
) -> PreparedContext:
    if context_window_tokens < 1:
        raise ValueError("context_window_tokens must be positive")
    if not 0 < compression_threshold <= 1:
        raise ValueError("compression_threshold must be in (0, 1]")
    estimated = estimate_tokens(text)
    requested = estimated >= context_window_tokens * compression_threshold
    prepared = compressor(text) if requested else text
    prepared_estimate = estimate_tokens(prepared)
    if prepared_estimate > context_window_tokens:
        raise ContextTooLargeError(
            f"context_too_large: estimated {prepared_estimate} tokens exceeds "
            f"the {context_window_tokens} token window"
        )
    return PreparedContext(prepared, prepared_estimate, requested)


def _is_chinese(codepoint: int) -> bool:
    return any(
        start <= codepoint <= end
        for start, end in (
            (0x3400, 0x4DBF),
            (0x4E00, 0x9FFF),
            (0x20000, 0x2EBEF),
            (0x30000, 0x323AF),
        )
    )
