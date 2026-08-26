from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class UserVisibleAgentOutput:
    process: dict[str, Any]
    final_response: str
    show_process: bool = True
    process_collapsed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "process": self.process,
            "final_response": self.final_response,
            "show_process": self.show_process,
            "process_collapsed": self.process_collapsed,
        }
