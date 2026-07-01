from tools.camera_scene import CameraSceneTool


def test_camera_definition_forbids_recapture_after_successful_observation():
    description = CameraSceneTool().definition.description

    assert "successful camera_scene observation" in description
    assert "do not call camera_scene again" in description
    assert "insufficient" in description


def test_camera_definition_reports_visible_missing_and_uncertain_information():
    description = CameraSceneTool().definition.description

    assert "visible" in description
    assert "missing" in description
    assert "uncertain" in description
