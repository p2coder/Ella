from pathlib import Path

from runtime.interactions import InteractionBroker
from tools.ask_user_question import AskUserQuestionTool
from tools.camera_scene import CameraSceneTool
from tools.document_write import DocumentWriteTool
from tools.plan import PlanWrittenTool
from tools.screen_scene import ScreenSceneTool
from tools.verification import (
    ArtifactExistsTool,
    DocumentReadTool,
    ToolObservationCheckTool,
)
from tools.web_research import WebPageReadTool, WebSearchTool


def _definitions(tmp_path: Path):
    return (
        PlanWrittenTool(store=None).definition,
        AskUserQuestionTool(InteractionBroker()).definition,
        WebSearchTool().definition,
        WebPageReadTool().definition,
        DocumentWriteTool(tmp_path).definition,
        CameraSceneTool().definition,
        ScreenSceneTool().definition,
        ArtifactExistsTool(tmp_path).definition,
        DocumentReadTool(tmp_path).definition,
        ToolObservationCheckTool(lambda _: ()).definition,
    )


def test_high_decision_cost_tools_expose_complete_new_descriptions(tmp_path):
    for definition in _definitions(tmp_path):
        description = definition.description
        assert description.startswith("Purpose:")
        assert "Use when:" in description
        assert "Do not use when:" in description
        assert "Execution behavior:" in description


def test_description_changes_do_not_change_tool_schemas(tmp_path):
    for definition in _definitions(tmp_path):
        assert definition.input_schema["type"] == "object"
        assert definition.output_schema["type"] == "object"


def test_runtime_selection_metadata_is_not_added(tmp_path):
    for definition in _definitions(tmp_path):
        serialized = definition.to_dict()
        assert "selection_policy" not in serialized
        assert "selection_order" not in serialized


def test_user_question_description_makes_answer_provenance_explicit():
    description = AskUserQuestionTool(InteractionBroker()).definition.description

    assert "direct user-provided information" in description
    assert "Task identified by task_id" in description
    assert "do not claim it belongs to another execution context" in description
    assert "later phase" in description


def test_user_question_description_prefers_but_does_not_require_recommendation():
    description = AskUserQuestionTool(InteractionBroker()).definition.description

    assert "preferably mark one best option" in description
    assert "may omit a recommendation" in description
    assert "must not mark more than one" in description
