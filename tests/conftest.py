import pytest

from config import config as user_config


@pytest.fixture(autouse=True)
def mock_safe_user_config(monkeypatch):
    """Keep unit tests independent from the developer's local device settings."""
    defaults = {
        "MODEL_PROVIDER": "qwen",
        "QWEN_API_KEY": None,
        "DEEPSEEK_API_KEY": None,
        "USE_REAL_PROVIDERS": False,
        "MIC_ENABLED": False,
        "MIC_ALWAYS_LISTENING": False,
        "CAMERA_ENABLED": False,
        "DEBUG_STORE_RAW_MEDIA": False,
    }
    for name, value in defaults.items():
        monkeypatch.setattr(user_config, name, value)
