from dataclasses import dataclass
from pathlib import Path

from sessions.completion import TaskCompletionPackage


@dataclass(frozen=True, slots=True)
class MemoryManagementRequest:
    completion: TaskCompletionPackage

    @classmethod
    def from_completion(
        cls,
        completion: TaskCompletionPackage,
    ) -> "MemoryManagementRequest":
        return cls(completion=completion)

    @property
    def task_id(self) -> str:
        return self.completion.context.task_id

    @property
    def session_id(self) -> str:
        return self.completion.context.session_id

    @property
    def trace_id(self) -> str:
        return self.completion.context.trace_id


@dataclass(frozen=True, slots=True)
class MemoryWriteResult:
    action: str
    memory_path: Path


@dataclass(frozen=True, slots=True)
class MemoryManager:
    memory_path: Path = Path("memory/memory.md")

    def handle(self, request: MemoryManagementRequest) -> MemoryWriteResult:
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        with self.memory_path.open("a", encoding="utf-8") as memory_file:
            memory_file.write(self._format_record(request))
        return MemoryWriteResult(action="appended", memory_path=self.memory_path)

    def _format_record(self, request: MemoryManagementRequest) -> str:
        completion = request.completion
        final_response = completion.user_visible_output.final_response
        return (
            f"## Task {request.task_id}\n"
            f"- session_id: {request.session_id}\n"
            f"- trace_id: {request.trace_id}\n"
            f"- summary: {completion.summary}\n"
            f"- final_response: {final_response}\n"
            "\n"
        )
