from contextlib import asynccontextmanager
import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Request

from nim_router.config import get_nvidia_keys, get_openrouter_key, get_opencode_key
from nim_router.engine import ModelRouter
from nim_router.logger import logger

_router_instance: Optional[ModelRouter] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _router_instance
    nvidia_keys = get_nvidia_keys()
    openrouter_key = get_openrouter_key()
    opencode_key = get_opencode_key()

    if not nvidia_keys and not openrouter_key and not opencode_key:
        logger.warning("No API keys found in environment (.env). Please configure NVIDIA_API_KEYS, OPENROUTER_API_KEY, or OPENCODE_API_KEY.")

    _router_instance = ModelRouter(api_key=nvidia_keys, openrouter_key=openrouter_key, opencode_key=opencode_key)
    await _router_instance.initialize()
    yield
    logger.info("nim-router shutting down")

def create_app() -> FastAPI:
    app = FastAPI(title="NIM Router", lifespan=lifespan)

    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "total_models": len(_router_instance.models) if _router_instance else 0,
            "healthy_pool_size": len(_router_instance._healthy_pool) if _router_instance else 0
        }

    @app.get("/models")
    @app.get("/v1/models")
    async def list_models():
        if not _router_instance:
            return {"error": "Router not initialized"}

        data = [{"id": "nim-free", "object": "model", "owned_by": "nim-router"}]

        nvidia_models = sorted([m.get("id") for m in _router_instance.models if m.get("id") and _router_instance._get_provider_name(m.get("id")) == "NVIDIA"])
        openrouter_models = sorted([m.get("id") for m in _router_instance.models if m.get("id") and _router_instance._get_provider_name(m.get("id")) == "OpenRouter"])
        opencode_models = sorted([m.get("id") for m in _router_instance.models if m.get("id") and _router_instance._get_provider_name(m.get("id")) == "OpenCode"])

        for provider_name, model_group in [("NVIDIA", nvidia_models), ("OpenRouter", openrouter_models), ("OpenCode", opencode_models)]:
            for mid in model_group:
                display_id = f"[{provider_name}] {mid}"
                data.append({"id": display_id, "object": "model", "owned_by": provider_name.lower()})
                if mid != display_id:
                    data.append({"id": mid, "object": "model", "owned_by": provider_name.lower()})

        return {"object": "list", "data": data}

    @app.get("/v1/models/{model_id:path}")
    @app.get("/models/{model_id:path}")
    async def get_model(model_id: str):
        clean_id = model_id
        for prefix in ("[NVIDIA] ", "[OpenRouter] ", "[OpenCode] "):
            if clean_id.startswith(prefix):
                clean_id = clean_id[len(prefix):].strip()
        provider = _router_instance._get_provider_name(clean_id) if _router_instance else "nim-router"
        return {"id": model_id, "object": "model", "owned_by": provider.lower()}

    @app.get("/api/tags")
    async def get_tags():
        if not _router_instance:
            return {"models": []}

        tags = [{"name": "nim-free", "model": "nim-free", "modified_at": "2026-08-30T00:00:00Z", "size": 0}]

        nvidia_models = sorted([m.get("id") for m in _router_instance.models if m.get("id") and _router_instance._get_provider_name(m.get("id")) == "NVIDIA"])
        openrouter_models = sorted([m.get("id") for m in _router_instance.models if m.get("id") and _router_instance._get_provider_name(m.get("id")) == "OpenRouter"])
        opencode_models = sorted([m.get("id") for m in _router_instance.models if m.get("id") and _router_instance._get_provider_name(m.get("id")) == "OpenCode"])

        for provider_name, model_group in [("NVIDIA", nvidia_models), ("OpenRouter", openrouter_models), ("OpenCode", opencode_models)]:
            for mid in model_group:
                display_id = f"[{provider_name}] {mid}"
                tags.append({"name": display_id, "model": display_id, "modified_at": "2026-08-30T00:00:00Z", "size": 0})
                if mid != display_id:
                    tags.append({"name": mid, "model": mid, "modified_at": "2026-08-30T00:00:00Z", "size": 0})

        return {"models": tags}

    @app.post("/api/show")
    @app.post("/show")
    async def show_model_details(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        model_name = body.get("name") or body.get("model") or "nim-free"
        return {
            "modelfile": f"# nim-router virtual model\nFROM {model_name}",
            "parameters": "stop \"<|im_end|>\"",
            "template": "{{ .System }}\n{{ .Prompt }}",
            "details": {
                "parent_model": "",
                "format": "gguf",
                "family": "llama",
                "families": ["llama"],
                "parameter_size": "70B",
                "quantization_level": "Q4_K_M"
            },
            "model_info": {}
        }

    @app.get("/api/ps")
    async def get_running_ps():
        return {"models": []}

    @app.get("/api/version")
    async def get_version():
        return {"version": "1.0.0"}

    @app.get("/props")
    @app.get("/v1/props")
    async def get_props():
        return {}

    @app.post("/refresh")
    async def refresh_models():
        if not _router_instance:
            raise HTTPException(status_code=500, detail="Router not initialized")
        await _router_instance.refresh_models()
        return {
            "message": "Models refreshed successfully",
            "working_models": len(_router_instance.models),
            "models": [m.get("id") for m in _router_instance.models if m.get("id")]
        }

    @app.post("/v1/chat/completions")
    @app.post("/chat/completions")
    async def chat_completions(request: Request):
        return await _router_instance.handle_request(request)

    return app
