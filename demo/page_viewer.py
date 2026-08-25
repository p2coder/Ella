from html import escape
from pathlib import Path
from typing import Any, Mapping

from demo.display_snapshot import RunDisplaySnapshot


TEMPLATE_PATH = Path(__file__).resolve().parent / "static" / "display.html"


def render_snapshot_html(snapshot: RunDisplaySnapshot | Mapping[str, Any]) -> str:
    data = _snapshot_data(snapshot)
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    values = {
        "user_input": _value(data, "user_input"),
        "transcript": _value(data, "transcript"),
        "captured_frame_reference": _value(data, "captured_frame_reference"),
        "image_status": _value(data, "image_status"),
        "scene_summary": _value(data, "scene_summary"),
        "visible_items": _join_items(data.get("visible_items", ())),
        "task_goal": _value(data, "task_goal"),
        "task_formulation_prompt_text": _value(
            data,
            "task_formulation_prompt_text",
        ),
        "execution_decision_prompt_text": _value(
            data,
            "execution_decision_prompt_text",
        ),
        "final_response_prompt_text": _value(data, "final_response_prompt_text"),
        "tool_results_summary": _value(data, "tool_results_summary"),
        "final_response": _value(data, "final_response"),
        "memory_status": _value(data, "memory_status"),
    }
    return template.format(**values)


class LocalPageViewer:
    def write_snapshot(
        self,
        snapshot: RunDisplaySnapshot | Mapping[str, Any],
        output_path: Path,
    ) -> Path:
        output_path.write_text(render_snapshot_html(snapshot), encoding="utf-8")
        return output_path


def _snapshot_data(snapshot: RunDisplaySnapshot | Mapping[str, Any]) -> dict[str, Any]:
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
