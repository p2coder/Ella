from pathlib import Path

from config import config
from config.settings import load_settings


def test_default_storage_paths_are_derived_from_project_root() -> None:
    project_root = Path(__file__).resolve().parents[2]

    assert config.PROJECT_ROOT == project_root
    assert config.STORAGE_ROOT == project_root
    assert config.MEMORY_PATH == project_root / "memory" / "memory.md"
    assert config.TRACE_DIRECTORY == project_root / "trace"
    assert config.TASK_CHECKPOINT_DIRECTORY == project_root / "output" / "tasks"
    assert config.DISPLAY_DIRECTORY == project_root / "output" / "display"
    assert config.RAW_MEDIA_DIRECTORY == project_root / "output" / "raw_media"


def test_settings_expose_configured_storage_paths() -> None:
    settings = load_settings()

    assert settings.memory_path == config.MEMORY_PATH
    assert settings.trace_directory == config.TRACE_DIRECTORY
    assert settings.task_checkpoint_directory == config.TASK_CHECKPOINT_DIRECTORY
    assert settings.display_directory == config.DISPLAY_DIRECTORY
    assert settings.raw_media_directory == config.RAW_MEDIA_DIRECTORY


def test_storage_path_overrides_are_normalized(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "ELLA_MEMORY_PATH": tmp_path / "memory.md",
            "ELLA_TRACE_DIRECTORY": tmp_path / "trace",
            "ELLA_TASK_CHECKPOINT_DIRECTORY": tmp_path / "tasks",
            "ELLA_DISPLAY_DIRECTORY": tmp_path / "display",
            "ELLA_RAW_MEDIA_DIRECTORY": tmp_path / "raw_media",
        }
    )

    assert settings.memory_path == (tmp_path / "memory.md").resolve()
    assert settings.trace_directory == (tmp_path / "trace").resolve()
