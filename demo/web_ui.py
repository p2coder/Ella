from dataclasses import dataclass
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from pathlib import PurePosixPath
import json
import re
import sys
from threading import Lock
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit

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


class _QuietClientDisconnectMixin:
    def handle_error(self, request: Any, client_address: Any) -> None:
        error = sys.exception()
        if isinstance(error, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


class LocalWebUI:
    def __init__(self, app_runtime: AppRuntime) -> None:
        self._app_runtime = app_runtime
        self._lock = Lock()
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._task_inputs: dict[str, str] = {}
        self._task_errors: dict[str, str] = {}

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
            handle = self._app_runtime.submit_text(normalized_text)
        except Exception as error:
            return WebUIResponse(
                status=500,
                body=render_web_ui_shell(
                    form_error=f"Ella could not complete the task: {error}",
                ),
            )
        with self._lock:
            self._task_inputs[handle.task_id] = normalized_text
        return self.task_status(handle.task_id)

    def task_status(self, task_id: str) -> WebUIResponse:
        try:
            task = self._app_runtime.get_task(task_id)
        except KeyError:
            return WebUIResponse(
                status=404,
                body=render_web_ui_shell(form_error="Task not found."),
            )
        with self._lock:
            data = dict(self._snapshots.get(task_id, {}))
            user_input = self._task_inputs.get(task_id, "")
            task_error = self._task_errors.get(task_id, "")
        display_snapshot = task.get("display_snapshot")
        if isinstance(display_snapshot, Mapping):
            data.update(display_snapshot)
        data.update(
            {
                "user_input": data.get("user_input", user_input),
                "task_id": task_id,
                "task_state": task["state"],
                "goal_state": task.get("goal_state") or "",
                "terminal_execution_state": (
                    task.get("terminal_execution_state") or ""
                ),
                "pending_questions": task.get("pending_questions") or (),
                "paused_from_state": task.get("paused_from_state") or "",
                "terminal_outcome": task.get("terminal_outcome") or "",
            }
        )
        return WebUIResponse(
            status=200,
            body=render_web_ui_shell(data, form_error=task_error),
        )

    def control_task(self, task_id: str, action: str) -> WebUIResponse:
        controls = {
            "pause": self._app_runtime.pause,
            "resume": self._app_runtime.resume,
            "kill": self._app_runtime.kill,
        }
        control = controls.get(action)
        if control is None:
            return WebUIResponse(
                status=400,
                body=render_web_ui_shell(form_error="Unknown task control."),
            )
        try:
            result = control(task_id, reason="requested from local web UI")
        except KeyError:
            return WebUIResponse(
                status=404,
                body=render_web_ui_shell(form_error="Task not found."),
            )
        if not result.accepted:
            with self._lock:
                self._task_errors[task_id] = result.message
            response = self.task_status(task_id)
            return WebUIResponse(status=409, body=response.body)
        return self.task_status(task_id)

    def submit_microphone(self) -> WebUIResponse:
        try:
            handle, transcript = self._app_runtime.submit_microphone()
            with self._lock:
                self._task_inputs[handle.task_id] = transcript
            return self.task_status(handle.task_id)
        except Exception as error:
            return WebUIResponse(
                status=500,
                body=render_web_ui_shell(
                    form_error=(
                        "Ella could not complete the microphone task: "
                        f"{error}"
                    ),
                ),
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
        parsed = urlsplit(path)
        if normalized_method == "GET" and parsed.path == "/":
            return WebUIResponse(status=200, body=render_web_ui_shell())
        if normalized_method == "GET" and parsed.path == "/task":
            task_id = parse_qs(parsed.query).get("task_id", [""])[0]
            return self.task_status(task_id)
        if normalized_method == "GET" and parsed.path == "/tasks":
            return WebUIResponse(
                status=200,
                body=json.dumps(
                    self._app_runtime.task_snapshot(),
                    ensure_ascii=False,
                    default=str,
                ),
                content_type="application/json; charset=utf-8",
            )
        if normalized_method == "POST" and parsed.path == "/microphone":
            return self.submit_microphone()
        if normalized_method == "POST" and parsed.path == "/tasks":
            if content_type.split(";", 1)[0] != "application/json":
                return WebUIResponse(
                    415,
                    json.dumps({"error": "unsupported_content_type"}),
                    "application/json; charset=utf-8",
                )
            try:
                document = json.loads(body.decode("utf-8"))
                handle = self._app_runtime.submit_text(str(document["input"]))
                task = self._app_runtime.get_task(handle.task_id)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                return WebUIResponse(
                    400,
                    json.dumps({"error": str(error)}),
                    "application/json; charset=utf-8",
                )
            return WebUIResponse(
                202,
                json.dumps(
                    {
                        "task_id": handle.task_id,
                        "state": task["state"],
                        "auto_start": True,
                    },
                    ensure_ascii=False,
                ),
                "application/json; charset=utf-8",
            )
        if normalized_method == "POST" and parsed.path == "/tasks/input":
            try:
                document = json.loads(body.decode("utf-8"))
                accepted = self._app_runtime.provide_input(
                    str(document["task_id"]),
                    str(document["correlation_key"]),
                    str(document["value"]),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                return WebUIResponse(
                    400,
                    json.dumps({"error": str(error)}),
                    "application/json; charset=utf-8",
                )
            return WebUIResponse(
                202 if accepted else 409,
                json.dumps({"accepted": accepted}),
                "application/json; charset=utf-8",
            )
        if normalized_method == "POST" and parsed.path == "/task/control":
            if content_type.split(";", 1)[0] != "application/x-www-form-urlencoded":
                return WebUIResponse(
                    status=415,
                    body=render_web_ui_shell(
                        form_error="Unsupported form content type.",
                    ),
                )
            form = parse_qs(body.decode("utf-8"), keep_blank_values=True)
            return self.control_task(
                form.get("task_id", [""])[0],
                form.get("action", [""])[0],
            )
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
    task_state = str(data.get("task_state") or "")
    task_id = str(data.get("task_id") or "")
    pause_enabled = task_state in {
        "created",
        "ready",
        "reasoning",
        "tool_execution",
    }
    resume_enabled = task_state == "paused"
    kill_enabled = bool(task_id) and task_state not in {
        "completed",
        "failed",
        "uncertain",
        "pause_requested",
        "killed",
        "delivered",
    }
    values = {
        "user_input": _value(data, "user_input"),
        "transcript_markup": _transcript_markup(data),
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
        "timing_summary": _value(data, "timing_summary"),
        "model_output": _value(data, "model_output") or _value(data, "final_response"),
        "total_duration": _total_duration(data),
        "token_usage": _metric_value(data.get("token_usage")),
        "cache_hit_rate": _metric_value(data.get("cache_hit_rate"), suffix="%"),
        "final_response": _value(data, "final_response"),
        "memory_status": _value(data, "memory_status"),
        "task_id": _value(data, "task_id"),
        "task_state": _value(data, "task_state"),
        "task_state_label": escape(task_state or "No active task"),
        "goal_state": _value(data, "goal_state"),
        "terminal_execution_state": _value(data, "terminal_execution_state"),
        "controls_hidden": "" if task_id else "hidden",
        "pause_disabled": "" if pause_enabled else "disabled",
        "resume_disabled": "" if resume_enabled else "disabled",
        "kill_disabled": "" if kill_enabled else "disabled",
        "paused_from_state": _value(data, "paused_from_state"),
        "terminal_outcome": _value(data, "terminal_outcome"),
        "delivery_status": _value(data, "delivery_status"),
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

    class LocalThreadingHTTPServer(
        _QuietClientDisconnectMixin,
        ThreadingHTTPServer,
    ):
        pass

    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if urlsplit(self.path).path == "/task-events":
                self._stream_task_events()
                return
            self._write_response(
                web_ui.handle_request(method="GET", path=self.path)
            )

        def _stream_task_events(self) -> None:
            raw_last_event_id = self.headers.get("Last-Event-ID")
            try:
                last_event_id = (
                    None
                    if raw_last_event_id is None
                    else int(raw_last_event_id)
                )
            except ValueError:
                last_event_id = None
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                for event in app_runtime.subscribe_task_events(last_event_id):
                    payload = json.dumps(
                        event,
                        ensure_ascii=False,
                        default=str,
                    )
                    event_id = event.get("event_id", "")
                    event_type = event.get("event_type", "message")
                    message = (
                        f"id: {event_id}\n"
                        f"event: {event_type}\n"
                        f"data: {payload}\n\n"
                    ).encode("utf-8")
                    self.wfile.write(message)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return

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

    server = LocalThreadingHTTPServer((host, port), RequestHandler)
    server.daemon_threads = True
    return server


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


def _metric_value(value: Any, *, suffix: str = "") -> str:
    if value is None:
        return "暂无数据"
    return escape(f"{value:,}{suffix}" if isinstance(value, int) else f"{value}{suffix}")


def _total_duration(data: Mapping[str, Any]) -> str:
    timing = data.get("timing")
    if not isinstance(timing, Mapping):
        return "执行中" if data.get("task_id") else "--"
    value = timing.get("end_to_end_duration_ms")
    if value is None:
        value = timing.get("total_execution_duration_ms")
    if value is None:
        return "执行中"
    seconds = max(0, round(float(value) / 1000))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def _transcript_markup(data: Mapping[str, Any]) -> str:
    transcript = data.get("transcript")
    user_input = data.get("user_input")
    if transcript is None or transcript == user_input:
        return ""
    return (
        '<div class="field">'
        '<span class="field-label">Transcript</span>'
        f'<p class="field-value">{escape(str(transcript))}</p>'
        "</div>"
    )


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
