from pathlib import Path


def test_app_runtime_registers_document_write_with_configured_directory() -> None:
    source = Path("app_runtime.py").read_text()

    assert "DocumentWriteTool(settings.document_directory)" in source
    assert source.count("DocumentWriteTool(settings.document_directory)") == 1
