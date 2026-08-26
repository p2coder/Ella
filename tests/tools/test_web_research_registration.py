import inspect

import app_runtime
from tools import WebPageReadTool, WebSearchTool


def test_web_research_tools_are_public_tool_types():
    assert WebSearchTool().name == "web_search"
    assert WebPageReadTool().name == "web_page_read"


def test_app_runtime_registers_research_tools_once():
    source = inspect.getsource(app_runtime.AppRuntime.create_default)

    assert source.count("tool_manager.register(WebSearchTool())") == 1
    assert source.count("tool_manager.register(WebPageReadTool())") == 1
