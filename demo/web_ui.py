from dataclasses import dataclass
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from pathlib import PurePosixPath
import re
from threading import Lock, Thread
from time import sleep
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


class LocalWebUI:
    def __init__(self, app_runtime: AppRuntime) -> None:
        self._app_runtime = app_runtime
        self._lock = Lock()
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._task_inputs: dict[str, str] = {}
        self._running_tasks: set[str] = set()
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
            if not hasattr(self._app_runtime, "submit_text"):
                result = self._app_runtime.run_text_with_display(normalized_text)
                return WebUIResponse(
                    status=200,
                    body=render_web_ui_shell(result.snapshot),
                )
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
        self._start_task(handle.task_id)
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
        data.update(
            {
                "user_input": data.get("user_input", user_input),
                "task_id": task_id,
                "task_state": task["state"],
                "active_step_ids": task.get("active_step_ids", ()),
                "waiting_condition": task.get("waiting_condition") or "",
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
        if action == "resume":
            self._resume_task(task_id)
        return self.task_status(task_id)

    def _resume_task(self, task_id: str) -> None:
        with self._lock:
            still_finishing = task_id in self._running_tasks
        if not still_finishing:
            self._start_task(task_id)
            return
        Thread(
            target=self._start_after_current_run,
            args=(task_id,),
            name=f"ella-resume-{task_id}",
            daemon=True,
        ).start()

    def _start_after_current_run(self, task_id: str) -> None:
        while True:
            with self._lock:
                if task_id not in self._running_tasks:
                    break
            sleep(0.01)
        self._start_task(task_id)

    def _start_task(self, task_id: str) -> None:
        with self._lock:
            if task_id in self._running_tasks:
                return
            self._running_tasks.add(task_id)
            self._task_errors.pop(task_id, None)
        Thread(
            target=self._run_task,
            args=(task_id,),
            name=f"ella-task-{task_id}",
            daemon=True,
        ).start()

    def _run_task(self, task_id: str) -> None:
        with self._lock:
            user_input = self._task_inputs.get(task_id, "")
        try:
            result = self._app_runtime.run_submitted_task_with_display(
                task_id,
                user_input=user_input,
            )
        except Exception as error:
            state = self._app_runtime.get_task(task_id)["state"]
            if state not in {"paused", "pause_requested", "killed"}:
                with self._lock:
                    self._task_errors[task_id] = (
                        f"Ella could not complete the task: {error}"
                    )
        else:
            with self._lock:
                self._snapshots[task_id] = result.snapshot.to_dict()
        finally:
            with self._lock:
                self._running_tasks.discard(task_id)

    def submit_microphone(self) -> WebUIResponse:
        try:
            result = self._app_runtime.run_microphone_with_display()
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
        parsed = urlsplit(path)
        if normalized_method == "GET" and parsed.path == "/":
            return WebUIResponse(status=200, body=render_web_ui_shell())
        if normalized_method == "GET" and parsed.path == "/task":
            task_id = parse_qs(parsed.query).get("task_id", [""])[0]
            return self.task_status(task_id)
        if normalized_method == "POST" and parsed.path == "/microphone":
            return self.submit_microphone()
        if normalized_method == "POST" and parsed.path in {"/submit", "/task/control"}:
            if content_type.split(";", 1)[0] != "application/x-www-form-urlencoded":
                return WebUIResponse(
                    status=415,
                    body=render_web_ui_shell(
                        form_error="Unsupported form content type.",
                    ),
                )
            form = parse_qs(body.decode("utf-8"), keep_blank_values=True)
            if parsed.path == "/task/control":
                return self.control_task(
                    form.get("task_id", [""])[0],
                    form.get("action", [""])[0],
                )
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
    task_state = str(data.get("task_state") or "")
    task_id = str(data.get("task_id") or "")
    pause_enabled = task_state in {
        "created",
        "formulating",
        "ready",
        "running",
        "waiting",
    }
    resume_enabled = task_state == "paused"
    kill_enabled = bool(task_id) and task_state not in {
        "succeeded",
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
        "task_formulation_prompt_text": _prompt_value(
            data,
            "task_formulation_prompt_text",
        ),
        "strategy_selection_prompt_text": _prompt_value(
            data,
            "strategy_selection_prompt_text",
        ),
        "execution_decision_prompt_text": _prompt_value(
            data,
            "execution_decision_prompt_text",
        ),
        "final_response_prompt_text": _prompt_value(
            data,
            "final_response_prompt_text",
        ),
        "tool_results_summary": _value(data, "tool_results_summary"),
        "timing_summary": _value(data, "timing_summary"),
        "final_response": _value(data, "final_response"),
        "memory_status": _value(data, "memory_status"),
        "task_id": _value(data, "task_id"),
        "task_state": _value(data, "task_state"),
        "task_state_label": escape(task_state or "No active task"),
        "controls_hidden": "" if task_id else "hidden",
        "pause_disabled": "" if pause_enabled else "disabled",
        "resume_disabled": "" if resume_enabled else "disabled",
        "kill_disabled": "" if kill_enabled else "disabled",
        "active_step_ids": _join_items(data.get("active_step_ids", ())),
        "waiting_condition": _value(data, "waiting_condition"),
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


def _prompt_value(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if value is None or not str(value).strip():
        return "Not invoked for this run."
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
