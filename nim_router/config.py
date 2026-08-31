import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

NIM_API_BASE = "https://integrate.api.nvidia.com/v1"
HEALTH_REFRESH_INTERVAL = 180
RATE_LIMIT_COOLDOWN = 30
CACHE_TTL = 180
PRIMARY_POOL_SIZE = 7
MODEL_MAX_RPM = 35
MODEL_MAX_CONCURRENCY = 4
