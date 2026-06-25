from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

from prompts.templates import TEMPLATES_BY_TYPE, PromptTemplate


class PromptType:
    TASK_FORMULATION = "TASK_FORMULATION"
    FINAL_RESPONSE = "FINAL_RESPONSE"
    STRATEGY_SELECTION = "STRATEGY_SELECTION"
    EXECUTION_DECISION = "EXECUTION_DECISION"


@dataclass(frozen=True, slots=True)
class PromptBuildResult:
    prompt: str
    prompt_type: str
    prompt_name: str
    context_keys: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "prompt_type": self.prompt_type,
            "prompt_name": self.prompt_name,
            "context_keys": self.context_keys,
        }


@dataclass(frozen=True, slots=True)
class PromptBlock:
    name: str
    content: Any
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("PromptBlock name must be non-empty")


@dataclass(frozen=True, slots=True)
class PromptFrame:
    prompt_type: str
    blocks: tuple[PromptBlock, ...]
    output_contract: str

    def __post_init__(self) -> None:
        if not self.prompt_type:
            raise ValueError("PromptFrame prompt_type must be non-empty")
        if not self.output_contract:
            raise ValueError("PromptFrame output_contract must be non-empty")

    @classmethod
    def from_blocks(
        cls,
        *,
        prompt_type: str,
        blocks: Sequence[PromptBlock],
        output_contract: str,
    ) -> "PromptFrame":
        return cls(
            prompt_type=prompt_type,
            blocks=tuple(blocks),
            output_contract=output_contract,
        )


class PromptEngine:
    def build(
        self,
        prompt_type: str,
        context: Mapping[str, Any] | None = None,
    ) -> PromptBuildResult:
        template = self._template_for(prompt_type)
        safe_context = dict(context or {})
        context_keys = tuple(sorted(str(key) for key in safe_context))
        prompt = redact_prompt_text(
            self._compose_prompt(template=template, context=safe_context)
        )

        return PromptBuildResult(
            prompt=prompt,
            prompt_type=prompt_type,
            prompt_name=template.name,
            context_keys=context_keys,
        )

    def _template_for(self, prompt_type: str) -> PromptTemplate:
        try:
            return TEMPLATES_BY_TYPE[prompt_type]
        except KeyError as error:
            raise ValueError(f"Unsupported prompt type: {prompt_type}") from error

    def _compose_prompt(
        self,
        *,
        template: PromptTemplate,
        context: Mapping[str, Any],
    ) -> str:
        frame = self._frame_for(template=template, context=context)
        block_text = "\n\n".join(
            f"{block.name}:\n{self._format_value(block.content)}"
            for block in frame.blocks
        )

        return (
            f"{block_text}\n\n"
            f"OutputContract:\n{frame.output_contract}"
        )

    def _frame_for(
        self,
        *,
        template: PromptTemplate,
        context: Mapping[str, Any],
    ) -> PromptFrame:
        context_content: Mapping[str, Any]
        if context:
            context_content = {
                key: context[key]
                for key in sorted(context)
            }
        else:
            context_content = {"none": "none"}

        return PromptFrame.from_blocks(
            prompt_type=template.name,
            blocks=(
                PromptBlock("SystemPrompt", template.system_prompt),
                PromptBlock("Instruction", template.instruction),
                PromptBlock("Context", context_content),
            ),
            output_contract=template.instruction,
        )

    def _format_value(self, value: Any) -> str:
        if isinstance(value, Mapping):
            return "{" + ", ".join(
                f"{key}: {self._format_value(item)}"
                for key, item in sorted(value.items())
            ) + "}"
        if isinstance(value, (list, tuple, set, frozenset)):
            return ", ".join(self._format_value(item) for item in value)
        if value is None:
            return "none"
        return str(value)


SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"),
    re.compile(
        r"\b(?:ELLA_QWEN_API_KEY|DASHSCOPE_API_KEY|QWEN_API_KEY|API_KEY)"
        r"\s*=\s*[A-Za-z0-9_\-]{16,}\b"
    ),
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.]{16,}\b"),
)


def redact_prompt_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted
