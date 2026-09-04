import pytest

from agent.context import AgentExecutionContext, CapabilityScope
from tools.web_research import WebPageReadTool, WebResponse, WebSearchTool


def context() -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-research",
        trace_id="trace-research",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ("web_search", "web_page_read")),
        permissions=("read_context",),
    )


def test_web_search_returns_bounded_source_metadata_without_network():
    html = b"""
    <div class="snippet" data-type="web">
      <div><a href="https://example.com/docs"><div class="search-snippet-title">Official docs</div></a>
      <div class="content">Persistence and durable execution.</div></div>
    </div>
    <div class="snippet" data-type="web">
      <div><a href="https://example.org/guide"><div class="search-snippet-title">Guide</div></a>
      <div class="content">A second source.</div></div>
    </div>
    """
    calls = []

    def transport(url, timeout, max_bytes):
        calls.append((url, timeout, max_bytes))
        return WebResponse(url, 200, "text/html", html)

    result = WebSearchTool(transport=transport).run(
        context(), {"query": "agent runtime persistence", "max_results": 1}
    )

    assert result.payload == {
        "status": "available",
        "query": "agent runtime persistence",
        "results": [
            {
                "title": "Official docs",
                "url": "https://example.com/docs",
                "snippet": "Persistence and durable execution.",
            }
        ],
    }
    assert len(calls) == 1


def test_web_page_read_extracts_visible_text_and_title_without_network():
    body = b"""
    <html><head><title>Runtime Docs</title><style>hidden</style></head>
    <body><main><h1>Pause and resume</h1><p>Tasks can resume from checkpoints.</p></main>
    <script>not visible</script></body></html>
    """

    def transport(url, timeout, max_bytes):
        return WebResponse(url, 200, "text/html; charset=utf-8", body)

    result = WebPageReadTool(transport=transport).run(
        context(), {"url": "https://example.com/docs", "max_characters": 500}
    )

    assert result.payload["status"] == "available"
    assert result.payload["title"] == "Runtime Docs"
    assert result.payload["text"] == "Pause and resume Tasks can resume from checkpoints."
    assert result.payload["truncated"] is False
    assert "hidden" not in result.payload["text"]


@pytest.mark.parametrize(
    "url",
    (
        "file:///etc/passwd",
        "http://localhost:8000/private",
        "http://127.0.0.1/private",
        "http://10.0.0.1/private",
        "http://[::1]/private",
    ),
)
def test_web_page_read_rejects_non_public_urls_before_transport(url):
    calls = []
    tool = WebPageReadTool(
        transport=lambda *args: calls.append(args) or WebResponse(url, 200, "text/plain", b"x")
    )

    with pytest.raises(ValueError, match="public|private"):
        tool.run(context(), {"url": url})

    assert calls == []


def test_transport_failure_returns_structured_unavailable_result():
    def unavailable(url, timeout, max_bytes):
        raise TimeoutError("timed out")

    result = WebSearchTool(transport=unavailable).run(
        context(), {"query": "current agent frameworks"}
    )

    assert result.payload["status"] == "unavailable"
    assert result.payload["results"] == ()
    assert result.payload["error"]["code"] == "web_search_failed"


def test_web_search_falls_back_to_public_github_repository_search():
    calls = []

    def transport(url, timeout, max_bytes):
        calls.append(url)
        if "search.brave.com" in url:
            return WebResponse(url, 429, "text/html", b"rate limited")
        return WebResponse(
            url,
            200,
            "application/json",
            b'{"items":[{"full_name":"langchain-ai/langgraph",'
            b'"html_url":"https://github.com/langchain-ai/langgraph",'
            b'"description":"Build resilient language agents as graphs.",'
            b'"homepage":"https://docs.langchain.com/oss/python/langgraph"}]}',
        )

    result = WebSearchTool(transport=transport).run(
        context(), {"query": "LangGraph persistence", "max_results": 5}
    )

    assert result.payload["status"] == "available"
    assert result.payload["results"][0]["title"] == "langchain-ai/langgraph"
    assert result.payload["results"][0]["url"] == (
        "https://github.com/langchain-ai/langgraph"
    )
    assert "GitHub repository" in result.payload["results"][0]["snippet"]
    assert len(calls) == 2


def test_web_search_caches_repeated_identical_queries():
    calls = []
    html = b'<div class="snippet" data-type="web"><div><a href="https://example.com/docs"><div class="search-snippet-title">Docs</div></a><div class="content">Source text.</div></div></div>'

    def transport(url, timeout, max_bytes):
        calls.append(url)
        return WebResponse(url, 200, "text/html", html)

    tool = WebSearchTool(transport=transport)
    first = tool.run(context(), {"query": "same query", "max_results": 3})
    second = tool.run(context(), {"query": "same query", "max_results": 3})

    assert first.payload == second.payload
    assert len(calls) == 1


def test_tool_definitions_explain_search_then_verify_boundary():
    search = WebSearchTool().definition
    reader = WebPageReadTool().definition

    assert search.name == "web_search"
    assert reader.name == "web_page_read"
    assert "web_page_read" in search.description
    assert "verify" in reader.description
    assert search.input_schema["additionalProperties"] is False
    assert reader.input_schema["additionalProperties"] is False
    assert search.idempotency.value == "idempotent"
    assert reader.idempotency.value == "idempotent"
