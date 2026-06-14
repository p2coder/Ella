from dataclasses import dataclass
import re
from typing import Any, Mapping

from prompts.templates import TEMPLATES_BY_TYPE, PromptTemplate


class PromptType:
    TASK_FORMULATION = "TASK_FORMULATION"
    FINAL_RESPONSE = "FINAL_RESPONSE"


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
        context_text = "\n".join(
            f"- {key}: {self._format_value(context[key])}"
            for key in sorted(context)
        )
        if not context_text:
            context_text = "- none"

        return (
            f"System:\n{template.system_prompt}\n\n"
            f"Instruction:\n{template.instruction}\n\n"
            f"Context:\n{context_text}"
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
