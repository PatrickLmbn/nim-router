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
    _router_instance.models = await _router_instance._discover_models()
    _router_instance._healthy_pool = _router_instance._build_healthy_pool()
    logger.success(f"nim-router started with {len(_router_instance.models)} working models in active pool")
    yield
    logger.info("nim-router shutting down")

def create_app() -> FastAPI:
    app = FastAPI(title="NVIDIA NIM Free Router", lifespan=lifespan)

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
        model_list = [m.get("id") for m in _router_instance.models if m.get("id")]
        all_ids = ["nim-free"] + model_list
        return {
            "object": "list",
            "data": [
                {"id": mid, "object": "model", "owned_by": "nvidia-nim"}
                for mid in all_ids
            ]
        }

    @app.get("/v1/models/{model_id:path}")
    @app.get("/models/{model_id:path}")
    async def get_model(model_id: str):
        return {"id": model_id, "object": "model", "owned_by": "nvidia-nim"}

    @app.get("/api/tags")
    async def get_tags():
        if not _router_instance:
            return {"models": []}
        model_list = [m.get("id") for m in _router_instance.models if m.get("id")]
        all_ids = ["nim-free"] + model_list
        return {
            "models": [
                {"name": mid, "model": mid, "modified_at": "2026-08-30T00:00:00Z", "size": 0}
                for mid in all_ids
            ]
        }

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
        _router_instance.models = await _router_instance._discover_models()
        _router_instance._healthy_pool = _router_instance._build_healthy_pool()
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
