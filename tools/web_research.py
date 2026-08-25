from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import ipaddress
import json
import socket
from threading import Lock
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from agent.context import AgentExecutionContext

from .base import ToolDefinition, ToolIdempotency, ToolResult


DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 1_000_000
MAX_SEARCH_RESULTS = 10
MAX_PAGE_CHARACTERS = 30_000
USER_AGENT = "Ella-Agent-Runtime/1.0 (+local research tool)"


@dataclass(frozen=True, slots=True)
class WebResponse:
    url: str
    status_code: int
    content_type: str
    body: bytes


WebTransport = Callable[[str, float, int], WebResponse]


@dataclass(frozen=True, slots=True)
class WebSearchTool:
    transport: WebTransport = field(default_factory=lambda: _default_transport)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    name: str = "web_search"
    allowed_roles: tuple[str, ...] = ("main_agent",)
    _cache: dict[tuple[str, int], tuple[dict[str, str], ...]] = field(
        default_factory=dict,
        compare=False,
        repr=False,
    )
    _cache_lock: Lock = field(default_factory=Lock, compare=False, repr=False)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Use to find current public web sources for research, comparison, "
                "or fact verification. Returns bounded result titles, URLs, and "
                "snippets; follow important results with web_page_read before "
                "making detailed claims. Do not use for private networks, local "
                "files, authenticated content, or as proof that a snippet is true."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Focused public-web search query.",
                    },
                    "max_results": {
                        "type": "number",
                        "minimum": 1,
                        "maximum": MAX_SEARCH_RESULTS,
                        "description": "Maximum number of results to return.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            input_examples=(
                {
                    "query": "LangGraph persistence pause resume official docs",
                    "max_results": 5,
                },
            ),
            output_schema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["available", "unavailable"],
                    },
                    "query": {"type": "string"},
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "url": {"type": "string"},
                                "snippet": {"type": "string"},
                            },
                            "required": ["title", "url", "snippet"],
                        },
                    },
                    "error": {"type": "object"},
                },
                "required": ["status", "query", "results"],
            },
            idempotency=ToolIdempotency.IDEMPOTENT,
        )

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict[str, object] | None = None,
    ) -> ToolResult:
        arguments = arguments or {}
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("query must be non-empty")
        limit = _bounded_integer(
            arguments.get("max_results", 5),
            name="max_results",
            maximum=MAX_SEARCH_RESULTS,
        )
        cache_key = (query.casefold(), limit)
        with self._cache_lock:
            cached = self._cache.get(cache_key)
        errors: list[str] = []
        if cached is None:
            results = self._try_brave(query, limit, errors)
            if not results:
                results = self._try_github(query, limit, errors)
            if results:
                cached = tuple(dict(item) for item in results)
                with self._cache_lock:
                    self._cache[cache_key] = cached
        if cached:
            payload = {
                "status": "available",
                "query": query,
                "results": [dict(item) for item in cached],
            }
        else:
            payload = _unavailable_payload(
                query=query,
                results=(),
                code="web_search_failed",
                message="; ".join(errors) or "no public search results found",
            )
        return ToolResult(self.name, context.task_id, context.trace_id, payload)

    def _try_brave(
        self,
        query: str,
        limit: int,
        errors: list[str],
    ) -> list[dict[str, str]]:
        try:
            response = self.transport(
                "https://search.brave.com/search?q=" + quote_plus(query),
                self.timeout_seconds,
                MAX_RESPONSE_BYTES,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code}")
            parser = _BraveSearchResultParser(limit)
            parser.feed(response.body.decode("utf-8", errors="replace"))
            if not parser.results:
                raise RuntimeError("no parseable results")
            return parser.results
        except Exception as error:
            errors.append(f"Brave search failed: {error}")
            return []

    def _try_github(
        self,
        query: str,
        limit: int,
        errors: list[str],
    ) -> list[dict[str, str]]:
        api_url = (
            "https://api.github.com/search/repositories?q="
            + quote_plus(f"{query} in:name,description,readme")
            + f"&per_page={limit}"
        )
        try:
            response = self.transport(
                api_url,
                self.timeout_seconds,
                MAX_RESPONSE_BYTES,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code}")
            document = json.loads(response.body.decode("utf-8"))
            results: list[dict[str, str]] = []
            for item in document.get("items", ())[:limit]:
                url = str(item.get("html_url", ""))
                _validate_public_url(url, resolve_dns=False)
                description = str(item.get("description") or "").strip()
                homepage = str(item.get("homepage") or "").strip()
                snippet = "GitHub repository"
                if description:
                    snippet += f": {description}"
                if homepage:
                    snippet += f" Project site: {homepage}"
                results.append(
                    {
                        "title": str(item.get("full_name") or item.get("name") or url),
                        "url": url,
                        "snippet": snippet,
                    }
                )
            if not results:
                raise RuntimeError("no repository results")
            return results
        except Exception as error:
            errors.append(f"GitHub repository search failed: {error}")
            return []


@dataclass(frozen=True, slots=True)
class WebPageReadTool:
    transport: WebTransport = field(default_factory=lambda: _default_transport)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    name: str = "web_page_read"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Use after web_search to read and verify one public source page. "
                "Returns the final URL, title, and bounded visible text suitable "
                "for evidence-based analysis and citations. Do not use for local "
                "or private-network URLs, authenticated pages, binary downloads, "
                "or claims not supported by the returned text."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Public HTTP or HTTPS source URL.",
                    },
                    "max_characters": {
                        "type": "number",
                        "minimum": 500,
                        "maximum": MAX_PAGE_CHARACTERS,
                        "description": "Maximum extracted text characters.",
                    },
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            input_examples=(
                {
                    "url": "https://example.com/docs",
                    "max_characters": 12000,
                },
            ),
            output_schema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["available", "unavailable"],
                    },
                    "url": {"type": "string"},
                    "title": {"type": "string"},
                    "text": {"type": "string"},
                    "truncated": {"type": "boolean"},
                    "error": {"type": "object"},
                },
                "required": ["status", "url", "title", "text", "truncated"],
            },
            idempotency=ToolIdempotency.IDEMPOTENT,
        )

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict[str, object] | None = None,
    ) -> ToolResult:
        arguments = arguments or {}
        url = str(arguments.get("url", "")).strip()
        _validate_public_url(url, resolve_dns=False)
        limit = _bounded_integer(
            arguments.get("max_characters", 12_000),
            name="max_characters",
            minimum=500,
            maximum=MAX_PAGE_CHARACTERS,
        )
        try:
            response = self.transport(url, self.timeout_seconds, MAX_RESPONSE_BYTES)
            _validate_public_url(response.url, resolve_dns=False)
            if response.status_code >= 400:
                raise RuntimeError(f"page returned HTTP {response.status_code}")
            media_type = response.content_type.split(";", 1)[0].strip().lower()
            if media_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                raise ValueError(f"unsupported page content type: {media_type}")
            decoded = response.body.decode("utf-8", errors="replace")
            if media_type == "text/plain":
                title = ""
                extracted = _normalize_text(decoded)
            else:
                parser = _ReadablePageParser()
                parser.feed(decoded)
                title = _normalize_text(" ".join(parser.title_parts))
                extracted = _normalize_text(" ".join(parser.text_parts))
            truncated = len(extracted) > limit
            payload = {
                "status": "available",
                "url": response.url,
                "title": title,
                "text": extracted[:limit],
                "truncated": truncated,
            }
        except Exception as error:
            payload = {
                "status": "unavailable",
                "url": url,
                "title": "",
                "text": "",
                "truncated": False,
                "error": {"code": "web_page_read_failed", "message": str(error)},
            }
        return ToolResult(self.name, context.task_id, context.trace_id, payload)


class _BraveSearchResultParser(HTMLParser):
    def __init__(self, limit: int) -> None:
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.results: list[dict[str, str]] = []
        self._result_depth = 0
        self._current: dict[str, str] | None = None
        self._active: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        classes = set(attributes.get("class", "").split())
        if (
            tag == "div"
            and "snippet" in classes
            and attributes.get("data-type") == "web"
            and self._result_depth == 0
            and len(self.results) < self.limit
        ):
            self._result_depth = 1
            self._current = {"title": "", "url": "", "snippet": ""}
            return
        if self._result_depth == 0:
            return
        if tag == "div":
            self._result_depth += 1
        if tag == "a" and self._current is not None and not self._current["url"]:
            self._current["url"] = attributes.get("href", "")
        if tag == "div" and "search-snippet-title" in classes:
            self._active = "title"
            self._parts = []
        elif tag == "div" and "content" in classes:
            self._active = "snippet"
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._active is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._result_depth == 0:
            return
        if self._active is not None and tag == "div" and self._current is not None:
            self._current[self._active] = _normalize_text(" ".join(self._parts))
            self._active = None
        if tag != "div":
            return
        self._result_depth -= 1
        if self._result_depth == 0 and self._current is not None:
            try:
                _validate_public_url(self._current["url"], resolve_dns=False)
            except ValueError:
                self._current = None
                return
            if self._current["title"] and self._current["url"]:
                self.results.append(self._current)
            self._current = None


class _ReadablePageParser(HTMLParser):
    _SKIPPED = {"script", "style", "noscript", "svg", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIPPED:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIPPED and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        else:
            self.text_parts.append(data)


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        _validate_public_url(target, resolve_dns=True)
        return super().redirect_request(req, fp, code, msg, headers, target)


def _default_transport(url: str, timeout: float, max_bytes: int) -> WebResponse:
    _validate_public_url(url, resolve_dns=True)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    opener = build_opener(_SafeRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError("web response exceeds configured size limit")
            final_url = response.geturl()
            _validate_public_url(final_url, resolve_dns=True)
            return WebResponse(
                url=final_url,
                status_code=response.status,
                content_type=response.headers.get_content_type(),
                body=body,
            )
    except HTTPError as error:
        raise RuntimeError(f"HTTP {error.code}") from error
    except (URLError, TimeoutError, socket.timeout) as error:
        raise RuntimeError(f"web transport failed: {error}") from error


def _validate_public_url(url: str, *, resolve_dns: bool) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("url must be a public HTTP or HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("url credentials are not allowed")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("local and private network URLs are not allowed")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise ValueError("local and private network URLs are not allowed")
    if resolve_dns:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
            )
        }
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise ValueError("url resolves to a local or private network address")


def _bounded_integer(
    value: object,
    *,
    name: str,
    maximum: int,
    minimum: int = 1,
) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    integer = int(value)
    if integer != value or not minimum <= integer <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return integer


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _unavailable_payload(
    *,
    query: str,
    results,
    code: str,
    message: str,
) -> dict[str, object]:
    return {
        "status": "unavailable",
        "query": query,
        "results": tuple(results),
        "error": {"code": code, "message": message},
    }
