from dataclasses import dataclass
import json
import re
from typing import Any, Mapping

from prompts.templates import TEMPLATES_BY_TYPE, PromptTemplate


WORKSPACE_CONTEXT_KEYS = frozenset(("workspace", "WorkSpace"))
MEMORY_CONTEXT_KEYS = frozenset(("memory", "memory_context", "Memory"))
USER_PROMPT_CONTEXT_KEYS = frozenset(("user_input", "user_prompt", "UserPrompt"))
# Cache-friendly workspace field order. Provider prefix caching (DeepSeek
# automatic context caching / DashScope context cache) reuses only the
# byte-identical head of the prompt, so a field that changes between two
# calls invalidates everything after it. Fields are therefore ordered:
#   whole-task stable → append-only shared history → per-node → per-wave →
#   per-decision variable.
# Unknown workspace keys are appended after these in sorted order, which keeps
# their position stable as well.
WORKSPACE_CACHE_ORDER = (
    "visible_tools",
    "visible_skills",
    "overall_goal",
    "task_id",
    "trace_id",
    "observations",
    "completion_criteria",
    "current_goal",
    "plan",
    "current_step",
    "decision_repair",
    "task_state",
)
WORKSPACE_SORTED_KEYS = ("visible_tools", "visible_skills")
SENSITIVE_FIELD_MARKERS = (
    "api_key",
    "authorization",
    "credential",
    "secret",
    "token",
    "raw_media",
    "raw_audio",
    "raw_image",
    "raw_frame",
    "raw_bytes",
)


class PromptType:
    FIRST_DECISION = "FIRST_DECISION"
    EXECUTION_DECISION = "EXECUTION_DECISION"
    VERIFICATION_DECISION = "VERIFICATION_DECISION"


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
        blocks = self._blocks_for(template=template, context=context)
        sections = [
            f"{name}:\n{self._format_value(content)}"
            for name, content in blocks
        ]
        sections.append(f"FinalOutputReminder:\n{template.final_output_reminder}")
        return "\n\n".join(sections)

    def _blocks_for(
        self,
        *,
        template: PromptTemplate,
        context: Mapping[str, Any],
    ) -> list[tuple[str, Any]]:
        blocks: list[tuple[str, Any]] = [("SystemPrompt", template.system_prompt)]
        if template.capability_policy:
            blocks.append(("GlobalCapabilityPolicy", template.capability_policy))
        blocks.extend(
            (
                ("PromptTypeInstruction", template.instruction),
                ("OutputContract", template.output_contract),
            )
        )

        memory_content = self._first_context_value(
            context,
            keys=MEMORY_CONTEXT_KEYS,
        )
        workspace_content = self._first_context_value(
            context,
            keys=WORKSPACE_CONTEXT_KEYS,
        )
        user_prompt_content = self._first_context_value(
            context,
            keys=USER_PROMPT_CONTEXT_KEYS,
        )
        remaining_context = {
            key: context[key]
            for key in sorted(context)
            if key not in MEMORY_CONTEXT_KEYS
            and key not in WORKSPACE_CONTEXT_KEYS
            and key not in USER_PROMPT_CONTEXT_KEYS
        }

        if memory_content is not None:
            blocks.append(("Memory", self._sanitize_prompt_content(memory_content)))
        if user_prompt_content is not None:
            blocks.append(
                ("UserPrompt", self._sanitize_prompt_content(user_prompt_content))
            )
        if remaining_context or not context:
            blocks.append(("Context", remaining_context or {"none": "none"}))
        if workspace_content is not None:
            blocks.append(("WorkSpace", self._sanitize_workspace(workspace_content)))
        return blocks

    def _sanitize_workspace(self, value: Any) -> Any:
        sanitized = self._sanitize_prompt_content(value)
        if not isinstance(sanitized, Mapping):
            return sanitized
        ordered: dict[str, Any] = {}
        for key in WORKSPACE_CACHE_ORDER:
            if key in sanitized:
                item = sanitized[key]
                ordered[key] = (
                    self._sort_named_items(item)
                    if key in WORKSPACE_SORTED_KEYS
                    else item
                )
        for key in sorted(sanitized):
            if key not in ordered:
                ordered[key] = sanitized[key]
        return ordered

    @staticmethod
    def _sort_named_items(value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            return value
        return tuple(
            sorted(
                value,
                key=lambda item: (
                    str(item.get("name", ""))
                    if isinstance(item, Mapping)
                    else str(item)
                ),
            )
        )

    def _first_context_value(
        self,
        context: Mapping[str, Any],
        *,
        keys: frozenset[str],
    ) -> Any | None:
        for key in sorted(keys):
            if key in context:
                return context[key]
        return None

    def _sanitize_prompt_content(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            safe_items: dict[str, Any] = {}
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
                key_text = str(key)
                if self._is_sensitive_field(key_text):
                    safe_items[key_text] = "[REDACTED]"
                else:
                    safe_items[key_text] = self._sanitize_prompt_content(item)
            return safe_items
        if isinstance(value, tuple):
            return tuple(self._sanitize_prompt_content(item) for item in value)
        if isinstance(value, list):
            return [self._sanitize_prompt_content(item) for item in value]
        if isinstance(value, (set, frozenset)):
            return tuple(
                sorted(
                    self._format_value(self._sanitize_prompt_content(item))
                    for item in value
                )
            )
        if isinstance(value, str):
            if self._looks_like_sensitive_path(value):
                return "[REDACTED]"
            return value
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return "[UNSUPPORTED_OBJECT]"

    def _is_sensitive_field(self, key: str) -> bool:
        normalized = key.lower()
        return any(marker in normalized for marker in SENSITIVE_FIELD_MARKERS)

    def _looks_like_sensitive_path(self, value: str) -> bool:
        return (
            value.startswith("file://")
            or value.startswith("/Users/")
            or value.startswith("/private/")
            or value.startswith("/var/")
            or value.startswith("/tmp/")
            or value.startswith("../")
            or "/../" in value
        )

    def _format_value(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=lambda _: "[UNSUPPORTED_OBJECT]",
        )


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
