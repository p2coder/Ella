from tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, tool_name: str) -> None:
        self._tools.pop(tool_name, None)

    def get(self, tool_name: str) -> Tool | None:
        return self._tools.get(tool_name)

    def list_names(self) -> tuple[str, ...]:
        return tuple(self._tools.keys())
