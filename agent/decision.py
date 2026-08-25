from dataclasses import dataclass
from typing import Any, Mapping


CALL_TOOL = "CALL_TOOL"
COMPLETE = "COMPLETE"
SUPPORTED_EXECUTION_ACTIONS = frozenset({CALL_TOOL, COMPLETE})


@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    action: str
    tool_name: str | None
    tool_input: dict[str, object] | None
    decision_reason: str
    completion_summary: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.action not in SUPPORTED_EXECUTION_ACTIONS:
            raise ValueError(
                f"unsupported execution decision action: {self.action}"
            )
        if not isinstance(self.decision_reason, str) or not self.decision_reason.strip():
            raise ValueError("decision_reason must be a non-empty string")
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        if self.action == CALL_TOOL:
            if not self.tool_name:
                raise ValueError("CALL_TOOL requires tool_name")
            if self.completion_summary is not None or self.evidence_refs:
                raise ValueError("CALL_TOOL must not include completion fields")
            return
        if self.tool_name is not None:
            raise ValueError("COMPLETE must not include tool_name")
        if self.tool_input not in (None, {}):
            raise ValueError("COMPLETE must not include tool_input")
        if not isinstance(self.completion_summary, str) or not self.completion_summary.strip():
            raise ValueError("COMPLETE requires completion_summary")
        if any(not isinstance(ref, str) or not ref.strip() for ref in self.evidence_refs):
            raise ValueError("evidence_refs must contain non-empty strings")

    @property
    def is_complete(self) -> bool:
        return self.action == COMPLETE

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "decision_reason": self.decision_reason,
            "completion_summary": self.completion_summary,
            "evidence_refs": self.evidence_refs,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ExecutionDecision":
        tool_input = value.get("tool_input")
        if tool_input is not None and not isinstance(tool_input, dict):
            raise ValueError("tool_input must be an object")
        evidence_refs = value.get("evidence_refs", ())
        if not isinstance(evidence_refs, (list, tuple)):
            raise ValueError("evidence_refs must be an array")
        return cls(
            action=str(value.get("action", "")),
            tool_name=value.get("tool_name"),
            tool_input=tool_input,
            decision_reason=str(value.get("decision_reason", "")),
            completion_summary=value.get("completion_summary"),
            evidence_refs=tuple(evidence_refs),
        )
