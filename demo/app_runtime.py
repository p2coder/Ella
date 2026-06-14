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
