from dataclasses import dataclass
from typing import Any, Mapping

from tasks.task import TaskIntent


CALL_TOOL = "CALL_TOOL"
SUBMIT_RESULT = "SUBMIT_RESULT"
SUPPORTED_EXECUTION_ACTIONS = frozenset({CALL_TOOL, SUBMIT_RESULT})


@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    action: str
    tool_name: str | None
    tool_input: dict[str, object] | None
    decision_reason: str
    completion_summary: str | None = None
    evidence_refs: tuple[str, ...] = ()
    final_response_draft: str | None = None

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
            if (
                self.completion_summary is not None
                or self.evidence_refs
                or self.final_response_draft is not None
            ):
                raise ValueError("CALL_TOOL must not include completion fields")
            return
        if self.tool_name is not None:
            raise ValueError("SUBMIT_RESULT must not include tool_name")
        if self.tool_input not in (None, {}):
            raise ValueError("SUBMIT_RESULT must not include tool_input")
        if not isinstance(self.completion_summary, str) or not self.completion_summary.strip():
            raise ValueError("SUBMIT_RESULT requires completion_summary")
        if (
            not isinstance(self.final_response_draft, str)
            or not self.final_response_draft.strip()
        ):
            raise ValueError("SUBMIT_RESULT requires final_response_draft")
        if any(not isinstance(ref, str) or not ref.strip() for ref in self.evidence_refs):
            raise ValueError("evidence_refs must contain non-empty strings")

    @property
    def is_submit_result(self) -> bool:
        return self.action == SUBMIT_RESULT

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "decision_reason": self.decision_reason,
            "completion_summary": self.completion_summary,
            "evidence_refs": self.evidence_refs,
            "final_response_draft": self.final_response_draft,
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
            final_response_draft=value.get("final_response_draft"),
        )


@dataclass(frozen=True, slots=True)
class FirstDecision:
    intent: TaskIntent | None
    action: ExecutionDecision

    def __post_init__(self) -> None:
        if self.intent is None and not (
            self.action.action == CALL_TOOL
            and self.action.tool_name == "ask_user_question"
        ):
            raise ValueError(
                "FirstDecision without intent must ask the user a question"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": None if self.intent is None else self.intent.to_dict(),
            "action": self.action.to_dict(),
        }
