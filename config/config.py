"""User-editable Ella runtime configuration.

API keys may be set here for local development, but environment variables are
recommended for secrets. Runtime parsing and validation remain in settings.py.
"""

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
