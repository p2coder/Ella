from html import escape
from pathlib import Path
from typing import Any, Mapping

from demo.display_snapshot import RunDisplaySnapshot


TEMPLATE_PATH = Path(__file__).resolve().parent / "static" / "web_ui.html"


class LocalWebUIShell:
    def render(
        self,
        snapshot: RunDisplaySnapshot | Mapping[str, Any] | None = None,
    ) -> str:
        return render_web_ui_shell(snapshot)


def render_web_ui_shell(
    snapshot: RunDisplaySnapshot | Mapping[str, Any] | None = None,
) -> str:
    data = _snapshot_data(snapshot)
    values = {
        "user_input": _value(data, "user_input"),
        "transcript": _value(data, "transcript"),
        "captured_frame_reference": _value(
            data,
            "captured_frame_reference",
        ),
        "image_status": _value(data, "image_status"),
        "scene_summary": _value(data, "scene_summary"),
        "visible_items": _join_items(data.get("visible_items", ())),
        "task_goal": _value(data, "task_goal"),
        "task_formulation_prompt_text": _value(
            data,
            "task_formulation_prompt_text",
        ),
        "final_response_prompt_text": _value(
            data,
            "final_response_prompt_text",
        ),
        "tool_results_summary": _value(data, "tool_results_summary"),
        "final_response": _value(data, "final_response"),
        "memory_status": _value(data, "memory_status"),
    }
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    for key, value in values.items():
        html = html.replace("{{" + key + "}}", value)
    return html


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
