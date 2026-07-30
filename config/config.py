"""User-editable Ella runtime configuration.

API keys may be set here for local development, but environment variables are
recommended for secrets. Runtime parsing and validation remain in settings.py.
"""

from pathlib import Path


# Storage paths
#
# All default paths are derived from this repository root, so moving or cloning
# the project does not require editing machine-specific absolute paths. Change
# STORAGE_ROOT only when runtime data should live outside the repository.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORAGE_ROOT = PROJECT_ROOT
OUTPUT_DIRECTORY = STORAGE_ROOT / "output"
MEMORY_PATH = STORAGE_ROOT / "memory" / "memory.md"
TRACE_DIRECTORY = STORAGE_ROOT / "trace"
PLAN_DIRECTORY = OUTPUT_DIRECTORY / "plans"
TASK_CHECKPOINT_DIRECTORY = OUTPUT_DIRECTORY / "tasks"
DISPLAY_DIRECTORY = OUTPUT_DIRECTORY / "display"
RAW_MEDIA_DIRECTORY = OUTPUT_DIRECTORY / "raw_media"

MODEL_PROVIDER = "qwen"

QWEN_API_KEY = None
QWEN_LLM_MODEL = "qwen-plus"
QWEN_MULTIMODAL_MODEL = "qwen-vl-plus"
QWEN_SPEECH_MODEL = "qwen3-asr-flash"


# MODEL_PROVIDER = "qwen"

# QWEN_API_KEY = None
# QWEN_LLM_MODEL = None
# QWEN_MULTIMODAL_MODEL = None
# QWEN_SPEECH_MODEL = None

# MIC_ENABLED = False
MIC_ENABLED = True
MIC_DEVICE = "default"
MIC_ALWAYS_LISTENING = True
MIC_CAPTURE_DURATION_SECONDS = 5
MIC_SAMPLE_RATE = 16_000
MIC_CHANNELS = 1

# CAMERA_ENABLED = False
CAMERA_ENABLED = True
CAMERA_DEVICE = "default"
CAMERA_BACKGROUND_INTERVAL_SECONDS = 5
CAMERA_TASK_FPS = 1

# USE_REAL_PROVIDERS = False
USE_REAL_PROVIDERS = True
DEBUG_STORE_RAW_MEDIA = True
# DEBUG_STORE_RAW_MEDIA = False
