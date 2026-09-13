from nim_router.schemas import ChatCompletionRequest
from nim_router.catalog import VISION_KEYWORDS, is_banned_model

CODING_KEYWORDS = (
    "code",
    "coder",
    "codestral",
    "starcoder",
    "deepseek-coder",
    "qwen-coder",
    "dev",
    "script",
    "north-mini-code",
)

CODING_FRONTIER_MODELS = (
    "llama-3.3-70b",
    "llama3.3-70b",
    "nemotron-3-super-120b",
    "nemotron-4-340b",
    "qwen-2.5-72b",
    "qwen2.5-72b",
    "gpt-oss-120b",
    "claude-3-5-sonnet",
)

REASONING_KEYWORDS = (
    "reasoning",
    "r1",
    "qwq",
    "think",
    "o1",
    "o3",
    "reasoner",
    "deepseek-r1",
    "math",
    "logic",
)

MOE_KEYWORDS = (
    "moe",
    "mixtral",
    "dbrx",
    "a3b",
    "a12b",
    "a55b",
    "deepseek-v3",
    "deepseek-v4",
    "dots-3",
    "ling-3",
)

CHAT_KEYWORDS = (
    "instruct",
    "chat",
    "gemma",
    "llama",
    "mistral",
    "qwen",
    "conversational",
    "spark",
    "mimo",
    "glm",
    "hy3",
    "hunyuan",
)

TOOL_KEYWORDS = (
    "llama-3.1",
    "llama-3.2",
    "llama-3.3",
    "llama3.1",
    "llama3.2",
    "llama3.3",
    "qwen-2.5",
    "qwen2.5",
    "mistral-large",
    "mistral-small",
    "mixtral-8x7b",
    "command-r",
    "nemotron-4",
    "nemotron-3-super",
    "gpt-4",
    "gpt-3.5",
    "claude-3",
    "gemini",
    "deepseek-v3",
    "deepseek-chat",
    "deepseek-coder",
    "hermes",
    "function",
    "tool",
)

def is_tool_model(model_id: str, provider: str = "", raw_meta: dict | None = None) -> bool:
    if is_banned_model(model_id):
        return False
    if raw_meta and isinstance(raw_meta, dict):
        params = raw_meta.get("supported_parameters") or []
        if "tools" in params or "tool_choice" in params:
            return True
    mid = model_id.lower().strip()
    return any(k in mid for k in TOOL_KEYWORDS)

def is_vision_model(model_id: str, raw_meta: dict | None = None) -> bool:
    if is_banned_model(model_id):
        return False
    if raw_meta and isinstance(raw_meta, dict):
        arch = raw_meta.get("architecture") or {}
        modality = str(arch.get("modality", "")).lower()
        if "image" in modality or "multimodal" in modality:
            return True
    mid = model_id.lower().strip()
    return any(k in mid for k in VISION_KEYWORDS)

def is_coding_model(model_id: str, raw_meta: dict | None = None) -> bool:
    if is_banned_model(model_id):
        return False
    mid = model_id.lower().strip()
    return any(k in mid for k in CODING_KEYWORDS) or any(k in mid for k in CODING_FRONTIER_MODELS)

def is_reasoning_model(model_id: str, raw_meta: dict | None = None) -> bool:
    if is_banned_model(model_id):
        return False
    if raw_meta and isinstance(raw_meta, dict):
        params = raw_meta.get("supported_parameters") or []
        if "reasoning" in params:
            return True
    mid = model_id.lower().strip()
    return any(k in mid for k in REASONING_KEYWORDS)

def is_moe_model(model_id: str) -> bool:
    if is_banned_model(model_id):
        return False
    mid = model_id.lower().strip()
    return any(k in mid for k in MOE_KEYWORDS)

def is_chat_model(model_id: str) -> bool:
    if is_banned_model(model_id):
        return False
    mid = model_id.lower().strip()
    return any(k in mid for k in CHAT_KEYWORDS)

def get_model_capabilities(model_id: str, provider: str = "", raw_meta: dict | None = None) -> dict[str, bool]:
    return {
        "tools": is_tool_model(model_id, provider, raw_meta),
        "coding": is_coding_model(model_id, raw_meta),
        "reasoning": is_reasoning_model(model_id, raw_meta),
        "vision": is_vision_model(model_id, raw_meta),
        "chat": is_chat_model(model_id),
        "moe": is_moe_model(model_id),
    }

def get_model_tasks(model_id: str, provider: str = "", raw_meta: dict | None = None) -> list[str]:
    caps = get_model_capabilities(model_id, provider, raw_meta)
    return [task for task, enabled in caps.items() if enabled]

def is_vision_request(request: ChatCompletionRequest) -> bool:
    for msg in request.messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("images"):
            return True
        content = msg.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    item_type = item.get("type", "")
                    if (
                        item_type in ("image_url", "image", "input_image")
                        or "image_url" in item
                        or "image" in item
                    ):
                        return True
        elif isinstance(content, dict):
            item_type = content.get("type", "")
            if (
                item_type in ("image_url", "image", "input_image")
                or "image_url" in content
                or "image" in content
            ):
                return True
    return False

def estimate_token_count(request: ChatCompletionRequest) -> int:
    total_words = 0
    for msg in request.messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            total_words += len(content.split())
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    total_words += len(item.get("text", "").split())
    return int(total_words / 0.75)

def extract_model_family(model_id: str) -> str:
    mid = (model_id or "").lower().strip()
    for prefix in ("[nvidia] ", "[openrouter] ", "[opencode] ", "[groq] ", "[cerebras] ", "[bai] ", "[category] "):
        if mid.startswith(prefix):
            mid = mid[len(prefix):].strip()

    if "nemotron" in mid:
        return "nemotron"
    if "qwq" in mid or "qwen" in mid:
        return "qwen"
    if "deepseek" in mid:
        return "deepseek"
    if any(k in mid for k in ("mistral", "codestral", "mixtral")):
        return "mistral"
    if "llama" in mid:
        return "llama"
    if "gemma" in mid:
        return "gemma"
    if "phi" in mid:
        return "phi"
    if "claude" in mid:
        return "claude"
    if "gpt" in mid:
        return "gpt"
    if "glm" in mid:
        return "glm"
    if "command" in mid:
        return "command"
    if "nova" in mid:
        return "nova"
    if "jamba" in mid:
        return "jamba"
    return "unknown"

def get_same_family_models(target_model_id: str, candidates: list[str]) -> list[str]:
    target_family = extract_model_family(target_model_id)
    if not target_family or target_family == "unknown":
        return []
    return [
        m for m in candidates
        if m != target_model_id and extract_model_family(m) == target_family
    ]
