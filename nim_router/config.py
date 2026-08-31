import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

NIM_API_BASE = "https://integrate.api.nvidia.com/v1"
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
OPENCODE_API_BASE = "https://opencode.ai/zen/v1"

HEALTH_REFRESH_INTERVAL = 180
RATE_LIMIT_COOLDOWN = 30
CACHE_TTL = 180
PRIMARY_POOL_SIZE = 7
MODEL_MAX_RPM = 35
MODEL_MAX_CONCURRENCY = 4

def get_nvidia_keys() -> list[str]:
    raw_keys = os.getenv("NVIDIA_API_KEYS", "") or os.getenv("NVIDIA_API_KEY", "")
    return [k.strip() for k in raw_keys.split(",") if k.strip()]

def get_openrouter_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "").strip()

def get_opencode_key() -> str:
    return os.getenv("OPENCODE_API_KEY", "").strip()

def get_primary_model() -> str:
    return os.getenv("PRIMARY_MODEL", "").strip() or os.getenv("MODEL", "nim-free").strip()

def get_api_keys() -> list[str]:
    return get_nvidia_keys()
