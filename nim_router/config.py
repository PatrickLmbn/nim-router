import os
import yaml
from dotenv import load_dotenv

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
_ENV_FILE = os.path.join(_BASE_DIR, ".env")
_SETTINGS_FILE = os.path.join(_BASE_DIR, "config", "settings.yaml")

load_dotenv(dotenv_path=_ENV_FILE)

NIM_API_BASE = "https://integrate.api.nvidia.com/v1"
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
OPENCODE_API_BASE = "https://opencode.ai/zen/v1"
GROQ_API_BASE = "https://api.groq.com/openai/v1"
CEREBRAS_API_BASE = "https://api.cerebras.ai/v1"
BAI_API_BASE = "https://api.b.ai/v1"

def _load_settings() -> dict:
    defaults = {
        "primary_model": "nim-auto",
        "routing_strategy": "fallback",
        "max_latency_threshold": 3.0,
        "health_refresh_interval": 180,
        "rate_limit_cooldown": 30,
        "primary_pool_size": 7,
        "model_max_rpm": 35,
        "model_max_concurrency": 4,
        "fallback_models": [],
    }
    example = _SETTINGS_FILE.replace(".yaml", ".yaml.example")
    if not os.path.exists(_SETTINGS_FILE) and os.path.exists(example):
        try:
            import shutil
            os.makedirs(os.path.dirname(_SETTINGS_FILE), exist_ok=True)
            shutil.copy(example, _SETTINGS_FILE)
        except Exception:
            pass
    if os.path.exists(_SETTINGS_FILE):
        try:
            with open(_SETTINGS_FILE, "r") as f:
                data = yaml.safe_load(f) or {}
            defaults.update({k: v for k, v in data.items() if v is not None})
        except Exception:
            pass
    return defaults

def update_setting(key: str, value):
    data = {}
    if os.path.exists(_SETTINGS_FILE):
        try:
            with open(_SETTINGS_FILE, "r") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            pass
    data[key] = value
    os.makedirs(os.path.dirname(_SETTINGS_FILE), exist_ok=True)
    with open(_SETTINGS_FILE, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)

def reload_env():
    if os.path.exists(_ENV_FILE):
        load_dotenv(dotenv_path=_ENV_FILE, override=True)

_s = _load_settings()
HEALTH_REFRESH_INTERVAL: int = int(_s["health_refresh_interval"])
RATE_LIMIT_COOLDOWN: int = int(_s["rate_limit_cooldown"])
CACHE_TTL: int = 180
PRIMARY_POOL_SIZE: int = int(_s["primary_pool_size"])
MODEL_MAX_RPM: int = int(_s["model_max_rpm"])
MODEL_MAX_CONCURRENCY: int = int(_s["model_max_concurrency"])
MAX_LATENCY_THRESHOLD: float = float(_s["max_latency_threshold"])

def get_nvidia_keys() -> list[str]:
    raw_keys = os.getenv("NVIDIA_API_KEYS", "") or os.getenv("NVIDIA_API_KEY", "")
    return [k.strip() for k in raw_keys.split(",") if k.strip()]

def get_openrouter_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "").strip()

def get_opencode_key() -> str:
    return os.getenv("OPENCODE_API_KEY", "").strip()

def get_groq_keys() -> list[str]:
    raw_keys = os.getenv("GROQ_API_KEYS", "") or os.getenv("GROQ_API_KEY", "")
    return [k.strip() for k in raw_keys.split(",") if k.strip()]

def get_cerebras_keys() -> list[str]:
    raw_keys = os.getenv("CEREBRAS_API_KEYS", "") or os.getenv("CEREBRAS_API_KEY", "")
    return [k.strip() for k in raw_keys.split(",") if k.strip()]

def get_bai_key() -> str:
    return os.getenv("BAI_API_KEY", "").strip()

def get_primary_model() -> str:
    env_val = os.getenv("PRIMARY_MODEL", "").strip()
    if env_val:
        return env_val
    return _load_settings().get("primary_model", "nim-auto") or "nim-auto"

def get_routing_strategy() -> str:
    return str(_load_settings().get("routing_strategy", "fallback")).strip().lower()

def get_fallback_models() -> list[str]:
    raw = _load_settings().get("fallback_models", [])
    if isinstance(raw, str):
        raw = [m.strip() for m in raw.split(",") if m.strip()]
    return [str(m).strip() for m in raw if str(m).strip()][:2]

def get_api_keys() -> list[str]:
    return get_nvidia_keys()

def get_health_refresh_interval() -> int:
    return max(30, int(_load_settings().get("health_refresh_interval", 180)))
