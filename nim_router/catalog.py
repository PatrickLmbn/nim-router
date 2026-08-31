import os
import json
from nim_router.logger import logger

VISION_KEYWORDS = (
    "vision",
    "-vl",
    "vl-",
    "_vl",
    "omni",
    "paligemma",
    "deplot",
    "neva",
    "florence",
    "kosmos",
    "fuyu",
    "llava",
    "multimodal",
    "pixtral",
)

BANNED_KEYWORDS = (
    "diffusion",
    "diffusiongemma",
    "embed",
    "reward",
    "clip",
    "detector",
    "parse",
    "rerank",
    "guard",
    "safety",
    "ising",
    "topic-control",
    "translate",
    "synthetic-video",
    "palmyra-med",
    "palmyra-fin",
)

BANNED_MODELS = {
    "google/diffusiongemma-26b-a4b-it",
    "nvidia/ising-calibration-1.5-31b",
    "nvidia/llama-3.1-nemoguard-8b-content-safety",
    "nvidia/llama-3.1-nemotron-safety-guard-8b-v3",
    "nvidia/nemotron-3.5-content-safety",
    "nvidia/llama-3.1-nemoguard-8b-topic-control",
    "nvidia/ai-synthetic-video-detector",
    "nvidia/nemotron-parse",
    "nvidia/nvclip",
    "nvidia/riva-translate-4b-instruct-v1.1",
    "nvidia/riva-translate-4b-instruct-v2",
    "nvidia/riva-translate-4b-instruct",
}

def is_banned_model(model_id: str) -> bool:
    if not model_id:
        return True
    mid = model_id.lower().strip()
    if mid in BANNED_MODELS:
        return True
    return any(k in mid for k in BANNED_KEYWORDS)

def load_fallback_models(latencies_dict: dict) -> list[dict]:
    base_dir = os.path.dirname(os.path.dirname(__file__))
    status_path = os.path.join(base_dir, "config", "models_status.json")
    example_path = os.path.join(base_dir, "config", "models_status.example.json")

    if not os.path.exists(status_path) and os.path.exists(example_path):
        try:
            os.makedirs(os.path.dirname(status_path), exist_ok=True)
            with open(example_path, "r") as src, open(status_path, "w") as dst:
                dst.write(src.read())
        except Exception:
            pass

    for path in [
        status_path,
        os.path.join(base_dir, "tests", "models_status.json"),
        example_path,
    ]:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                working = [mid for mid in data.get("working_models", []) if not is_banned_model(mid)]
                if working:
                    logger.info(f"Loaded {len(working)} working models from {path}")
                    for i, mid in enumerate(working):
                        latencies_dict[mid] = 0.3 + (i * 0.05)
                    return [{"id": mid} for mid in working]
            except Exception as e:
                logger.warning(f"Failed to read {path}: {e}")

    fallback_list = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "nvidia/nemotron-3.5-lightning-30b-a3b",
        "nvidia/nemotron-3-nano-30b-a3b",
        "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        "meta/llama-3.2-90b-vision-instruct",
        "meta/llama-3.2-11b-vision-instruct",
        "meta/muse-glimmer-30b",
        "google/gemma-4-31b-it",
        "minimaxai/minimax-m3",
        "poolside/laguna-xs-2.1",
    ]
    clean_fallback = [mid for mid in fallback_list if not is_banned_model(mid)]
    for i, mid in enumerate(clean_fallback):
        latencies_dict[mid] = 0.3 + (i * 0.05)
    return [{"id": mid} for mid in clean_fallback]
