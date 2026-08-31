from nim_router.schemas import ChatCompletionRequest
from nim_router.catalog import VISION_KEYWORDS, is_banned_model

def is_vision_model(model_id: str) -> bool:
    if is_banned_model(model_id):
        return False
    mid = model_id.lower().strip()
    return any(k in mid for k in VISION_KEYWORDS)

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
    total_chars = 0
    for msg in request.messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    total_chars += len(item.get("text", ""))
    return int(total_chars / 3.5)
