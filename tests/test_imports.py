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


def test_main_module_exposes_minimal_entrypoint():
    module = load_main_module()

    assert callable(module.main)
    assert module.main() == 0
