from dataclasses import dataclass
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from pathlib import PurePosixPath
import re
from typing import Any, Mapping
from urllib.parse import parse_qs

from app_runtime import AppRuntime
from demo.display_snapshot import RunDisplaySnapshot


TEMPLATE_PATH = Path(__file__).resolve().parent / "static" / "web_ui.html"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DISPLAY_IMAGE_PATTERN = re.compile(
    r"^data:image/(?:jpeg|png|webp|gif);base64,[A-Za-z0-9+/]+={0,2}$"
)


@dataclass(frozen=True, slots=True)
class WebUIResponse:
    status: int
    body: str
    content_type: str = "text/html; charset=utf-8"


class LocalWebUI:
    def __init__(self, app_runtime: AppRuntime) -> None:
        self._app_runtime = app_runtime

    def submit_text(self, input_text: str) -> WebUIResponse:
        normalized_text = input_text.strip()
        if not normalized_text:
            return WebUIResponse(
                status=400,
                body=render_web_ui_shell(
                    form_error="Please enter a message.",
                ),
            )

        try:
            result = self._app_runtime.run_text_with_display(normalized_text)
        except Exception as error:
            return WebUIResponse(
                status=500,
                body=render_web_ui_shell(
                    form_error=f"Ella could not complete the task: {error}",
                ),
            )
        return WebUIResponse(
            status=200,
            body=render_web_ui_shell(result.snapshot),
        )

    def handle_request(
        self,
        *,
        method: str,
        path: str,
        body: bytes = b"",
        content_type: str = "",
    ) -> WebUIResponse:
        normalized_method = method.upper()
        if normalized_method == "GET" and path == "/":
            return WebUIResponse(status=200, body=render_web_ui_shell())
        if normalized_method == "POST" and path == "/submit":
            if content_type.split(";", 1)[0] != "application/x-www-form-urlencoded":
                return WebUIResponse(
                    status=415,
                    body=render_web_ui_shell(
                        form_error="Unsupported form content type.",
                    ),
                )
            form = parse_qs(body.decode("utf-8"), keep_blank_values=True)
            return self.submit_text(form.get("user_input", [""])[0])
        return WebUIResponse(
            status=404,
            body=render_web_ui_shell(form_error="Page not found."),
        )


class LocalWebUIShell:
    def render(
        self,
        snapshot: RunDisplaySnapshot | Mapping[str, Any] | None = None,
    ) -> str:
        return render_web_ui_shell(snapshot)


def render_web_ui_shell(
    snapshot: RunDisplaySnapshot | Mapping[str, Any] | None = None,
    *,
    form_error: str = "",
) -> str:
    data = _snapshot_data(snapshot)
    values = {
        "user_input": _value(data, "user_input"),
        "transcript": _value(data, "transcript"),
        "captured_frame_reference": _value(
            data,
            "captured_frame_reference",
        ),
        "frame_markup": _frame_markup(data),
        "image_status": _value(data, "image_status"),
        "scene_summary": _value(data, "scene_summary"),
        "visible_items": _join_items(data.get("visible_items", ())),
        "task_goal": _value(data, "task_goal"),
        "tool_results_summary": _value(data, "tool_results_summary"),
        "final_response": _value(data, "final_response"),
        "memory_status": _value(data, "memory_status"),
        "form_error": escape(form_error),
    }
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    for key, value in values.items():
        html = html.replace("{{" + key + "}}", value)
    return html


def create_server(
    app_runtime: AppRuntime,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> ThreadingHTTPServer:
    web_ui = LocalWebUI(app_runtime)

    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._write_response(
                web_ui.handle_request(method="GET", path=self.path)
            )

        def do_POST(self) -> None:
            content_length = int(self.headers.get("Content-Length", "0"))
            self._write_response(
                web_ui.handle_request(
                    method="POST",
                    path=self.path,
                    body=self.rfile.read(content_length),
                    content_type=self.headers.get("Content-Type", ""),
                )
            )

        def _write_response(self, response: WebUIResponse) -> None:
            payload = response.body.encode("utf-8")
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), RequestHandler)


def _snapshot_data(
    snapshot: RunDisplaySnapshot | Mapping[str, Any] | None,
) -> dict[str, Any]:
    if snapshot is None:
        return {}
    if isinstance(snapshot, Mapping):
        return dict(snapshot)
    return dict(snapshot.to_dict())


def _value(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if value is None:
        return ""
    return escape(str(value))


def _join_items(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return escape(value)
    try:
        return escape(", ".join(str(item) for item in value))
    except TypeError:
        return escape(str(value))


def _frame_markup(data: Mapping[str, Any]) -> str:
    reference = data.get("captured_frame_reference")
    image_status = escape(str(data.get("image_status") or "text-only"))
    if isinstance(reference, str) and _is_displayable_frame_reference(reference):
        safe_reference = escape(reference, quote=True)
        return (
            '<img class="captured-frame" '
            f'src="{safe_reference}" '
            'alt="Captured camera frame">'
        )

    diagnostic = ""
    if isinstance(reference, str) and reference.startswith("mock://"):
        diagnostic = f'<span class="frame-reference">{escape(reference)}</span>'
    return (
        '<div class="frame-placeholder">'
        f'<strong>{image_status}</strong>'
        '<span>No captured frame is available.</span>'
        f"{diagnostic}"
        "</div>"
    )


def _is_displayable_frame_reference(reference: str) -> bool:
    if DISPLAY_IMAGE_PATTERN.fullmatch(reference):
        return True
    if "://" in reference or reference.startswith(("/", "\\")):
        return False
    path = PurePosixPath(reference)
    return (
        len(path.parts) > 1
        and path.parts[0] == "display"
        and ".." not in path.parts
    )
