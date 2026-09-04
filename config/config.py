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
TASK_CHECKPOINT_DIRECTORY = OUTPUT_DIRECTORY / "tasks"
DISPLAY_DIRECTORY = OUTPUT_DIRECTORY / "display"
RAW_MEDIA_DIRECTORY = OUTPUT_DIRECTORY / "raw_media"
DOCUMENT_DIRECTORY = OUTPUT_DIRECTORY / "documents"

# Optional per-tool observation TTL overrides. Values are seconds or None for
# observations that do not expire by time.
TOOL_RESULT_TTL_OVERRIDES = {}
WORKFLOW_MAX_SCRIPT_BYTES = 64 * 1024
WORKFLOW_MAX_WALL_SECONDS = 600
WORKFLOW_MAX_PARALLEL_CHILDREN = 8
WORKFLOW_MAX_TOTAL_CHILDREN = 32
WORKFLOW_MEMORY_LIMIT_BYTES = 64 * 1024 * 1024
WORKFLOW_MAX_RETURN_BYTES = 1024 * 1024
SUBAGENT_MAX_DEPTH = 4
SUBAGENT_MAX_ADVANCES = 50
SUBAGENT_MAX_TIMEOUT_SECONDS = 300

# MODEL_PROVIDER = "qwen"
MODEL_PROVIDER = "deepseek"

QWEN_API_KEY = None
QWEN_LLM_MODEL = "qwen-plus"
QWEN_LLM_RESPONSE_FORMAT = "json_object"
QWEN_LLM_ENABLE_THINKING = False
QWEN_MULTIMODAL_MODEL = "qwen-vl-plus"
QWEN_SPEECH_MODEL = "qwen3-asr-flash"

# Optional text LLM provider. Set MODEL_PROVIDER = "deepseek" to use it for
# reasoning and response generation. Camera and speech remain backed by Qwen.
DEEPSEEK_API_KEY = None
DEEPSEEK_LLM_MODEL = "deepseek-v4-pro"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_BYPASS_PROXY = True
DEEPSEEK_THINKING_ENABLED = True
DEEPSEEK_REASONING_EFFORT = "low"


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
