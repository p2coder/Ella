from dataclasses import dataclass
from pathlib import Path

from config.config import MEMORY_PATH
from tasks.completion import TaskCompletionPackage


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

@dataclass(frozen=True, slots=True)
class MemoryWriteResult:
    action: str
    memory_path: Path


@dataclass(frozen=True, slots=True)
class MemoryQueryResult:
    action: str
    memory_path: Path
    content: str


@dataclass(frozen=True, slots=True)
class MemoryManager:
    memory_path: Path = MEMORY_PATH

    def handle(self, request: MemoryManagementRequest) -> MemoryWriteResult:
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        with self.memory_path.open("a", encoding="utf-8") as memory_file:
            memory_file.write(self._format_record(request))
        return MemoryWriteResult(action="appended", memory_path=self.memory_path)

    def query(self) -> MemoryQueryResult:
        if not self.memory_path.exists():
            content = ""
        else:
            content = self.memory_path.read_text(encoding="utf-8")
        return MemoryQueryResult(
            action="loaded_all",
            memory_path=self.memory_path,
            content=content,
        )

    def _format_record(self, request: MemoryManagementRequest) -> str:
        completion = request.completion
        user_input = completion.user_visible_output.process.get("user_input")
        final_response = completion.user_visible_output.final_response
        user_input_record = (
            f"- user_input: {user_input}\n"
            if isinstance(user_input, str) and user_input
            else ""
        )
        return (
            f"## Task {request.task_id}\n"
            f"- task_id: {request.task_id}\n"
            f"{user_input_record}"
            f"- summary: {completion.summary}\n"
            f"- final_response: {final_response}\n"
            "\n"
        )
