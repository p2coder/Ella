from pathlib import Path
import importlib.util


ROOT = Path(__file__).resolve().parents[1]


def load_main_module():
    main_path = ROOT / "main.py"
    assert main_path.exists(), "main.py should exist at the repository root"

    spec = importlib.util.spec_from_file_location("ella_main", main_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_module_exposes_web_entrypoint(monkeypatch):
    module = load_main_module()
    runtime = object()
    calls = []

    monkeypatch.setattr(
        module.AppRuntime,
        "create_default",
        classmethod(lambda cls: runtime),
    )
    monkeypatch.setattr(module, "run_web_app", calls.append)

    assert callable(module.main)
    assert module.main() == 0
    assert calls == [runtime]


def test_final_ownership_modules_importable():
    from agent.decision import ExecutionDecision
    from agent.subagent import SubAgent
    from runtime.executor import CapabilityExecutor
    from tasks.factory import TaskFactory
    from tasks.state import StepState
    from tasks.task import Task

    assert all(
        (
            ExecutionDecision,
            SubAgent,
            CapabilityExecutor,
            TaskFactory,
            StepState,
            Task,
        )
    )
