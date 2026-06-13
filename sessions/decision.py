from dataclasses import dataclass


CALL_TOOL = "CALL_TOOL"
COMPLETE = "COMPLETE"
WAIT = "WAIT"
REPLAN = "REPLAN"

SUPPORTED_EXECUTION_ACTIONS = frozenset(
    {
        CALL_TOOL,
        COMPLETE,
        WAIT,
        REPLAN,
    }
)


@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    action: str
    tool_name: str | None
    tool_input: dict[str, object] | None
    reason: str
    is_complete: bool

    def __post_init__(self) -> None:
        if self.action not in SUPPORTED_EXECUTION_ACTIONS:
            raise ValueError(
                f"unsupported execution decision action: {self.action}"
            )
        if self.action == CALL_TOOL and not self.tool_name:
            raise ValueError("CALL_TOOL execution decision requires tool_name")
        if self.action == COMPLETE and self.tool_name is not None:
            raise ValueError(
                "COMPLETE execution decision must not include tool_name"
            )
        if self.action == COMPLETE and self.is_complete is not True:
            raise ValueError(
                "COMPLETE execution decision requires is_complete=True"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "reason": self.reason,
            "is_complete": self.is_complete,
        }
