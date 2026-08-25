import inspect

import app_runtime
import demo.cli_demo as cli_demo
from tools import WebPageReadTool, WebSearchTool


def test_web_research_tools_are_public_tool_types():
    assert WebSearchTool().name == "web_search"
    assert WebPageReadTool().name == "web_page_read"


def test_app_runtime_registers_research_tools_once():
    source = inspect.getsource(app_runtime.AppRuntime.create_default)

    assert source.count("tool_manager.register(WebSearchTool())") == 1
    assert source.count("tool_manager.register(WebPageReadTool())") == 1


def test_cli_assembly_registers_research_tools_once():
    source = inspect.getsource(cli_demo.DemoRuntime.create_default)

    assert source.count("tool_manager.register(WebSearchTool())") == 1
    assert source.count("tool_manager.register(WebPageReadTool())") == 1
