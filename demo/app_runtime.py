from pathlib import Path
from typing import Any


class AppRuntime:
    __slots__ = ("_demo_runtime",)

    def __init__(self, demo_runtime: Any) -> None:
        self._demo_runtime = demo_runtime

    @classmethod
    def create_default(cls, memory_path: Path) -> "AppRuntime":
        from demo.cli_demo import DemoRuntime

        return cls(DemoRuntime.create_default(memory_path))

    def run_text_with_display(self, input_text: str) -> Any:
        return self._demo_runtime.run_with_display(input_text)

    def control_task(self, command: Any) -> Any:
        return self._demo_runtime.control_task(command)

    def submit_text(self, text: str) -> Any:
        return self._demo_runtime.submit_text(text)

    def get_task(self, task_id: str) -> Any:
        return self._demo_runtime.get_task(task_id)

    def pause(self, task_id: str, reason: str = "") -> Any:
        return self._demo_runtime.pause(task_id, reason)

    def resume(self, task_id: str, reason: str = "") -> Any:
        return self._demo_runtime.resume(task_id, reason)

    def kill(self, task_id: str, reason: str = "") -> Any:
        return self._demo_runtime.kill(task_id, reason)

    def resolve_uncertain_as_failed(self, task_id: str, reason: str) -> Any:
        return self._demo_runtime.resolve_uncertain_as_failed(task_id, reason)
