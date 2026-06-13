from pathlib import Path

import demo.cli_demo as cli_demo
from providers.mock import MockLLMProvider


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_demo_assembly_obtains_llm_provider_through_factory(
    monkeypatch,
    tmp_path: Path,
):
    provider = MockLLMProvider()
    calls = []

    class RecordingProviderFactory:
        def llm(self):
            calls.append("llm")
            return provider

    monkeypatch.setattr(cli_demo, "ProviderFactory", RecordingProviderFactory)

    runtime = cli_demo.DemoRuntime.create_default(tmp_path / "memory.md")

    assert calls == ["llm"]
    assert runtime.event_runtime.llm_provider is provider
    assert runtime.event_runtime.main_agent.formulator.llm_provider is provider


def test_default_demo_uses_mock_llm_provider(tmp_path: Path):
    runtime = cli_demo.DemoRuntime.create_default(tmp_path / "memory.md")

    assert isinstance(runtime.event_runtime.llm_provider, MockLLMProvider)
    assert runtime.event_runtime.main_agent.formulator.llm_provider is (
        runtime.event_runtime.llm_provider
    )


def test_demo_runs_safely_when_real_provider_mode_has_no_api_key(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv("ELLA_USE_REAL_PROVIDERS", "true")
    monkeypatch.delenv("ELLA_QWEN_API_KEY", raising=False)
    monkeypatch.delenv("ELLA_QWEN_LLM_MODEL", raising=False)

    output = cli_demo.run_demo(memory_path=tmp_path / "memory.md")

    assert "[Final Answer]" in output
    assert "Give the user a short, necessary reminder before leaving." in output


def test_demo_assembly_does_not_import_qwen_directly():
    source = (PROJECT_ROOT / "demo" / "cli_demo.py").read_text(encoding="utf-8")

    assert "providers.qwen" not in source
