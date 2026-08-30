#!/usr/bin/env python3
import asyncio
import time
import logging
import os
import sys
import json
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("nim-router")

NIM_API_BASE = "https://integrate.api.nvidia.com/v1"
FAILOVER_MAX_ATTEMPTS = 3
HEALTH_REFRESH_INTERVAL = 300
CACHE_TTL = 300

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
    "diffusion",
)


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[dict]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    stop: Optional[list[str]] = None
    tools: Optional[list[dict]] = None


class ModelRouter:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.models: list[dict] = []
        self.model_index = 0
        self._lock = asyncio.Lock()
        self._health: dict[str, dict] = {}
        self._latencies: dict[str, float] = {}
        self._healthy_pool: list[str] = []
        self._pool_updated: float = 0

    def _is_vision_model(self, model_id: str) -> bool:
        mid = model_id.lower()
        return any(k in mid for k in VISION_KEYWORDS)

    def _is_vision_request(self, request: ChatCompletionRequest) -> bool:
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

    async def _probe_model(self, client: httpx.AsyncClient, model_id: str, sem: asyncio.Semaphore) -> tuple[bool, float]:
        async with sem:
            t0 = time.time()
            try:
                resp = await client.post(
                    f"{NIM_API_BASE}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model_id,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 1,
                        "temperature": 0.0
                    },
                    timeout=12.0
                )
                elapsed = round(time.time() - t0, 3)
                is_valid = resp.status_code in (200, 429)
                return is_valid, elapsed
            except Exception:
                return False, 999.0

    async def _discover_models(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{NIM_API_BASE}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                if response.status_code != 200:
                    logger.warning(f"Model discovery returned {response.status_code}")
                    return self._load_fallback_models()

                data = response.json()
                all_models = data.get("data", [])
                logger.info(f"Discovered {len(all_models)} total models from NVIDIA API. Probing on minimal scale...")

                sem = asyncio.Semaphore(10)
                valid_models = [m for m in all_models if m.get("id")]
                total_probes = len(valid_models)
                completed_count = 0
                lock = asyncio.Lock()

                async def probe_with_progress(m_obj):
                    nonlocal completed_count
                    mid = m_obj.get("id", "")
                    ok, latency = await self._probe_model(client, mid, sem)
                    async with lock:
                        completed_count += 1
                        pct = int((completed_count / total_probes) * 100)
                        bar_len = 30
                        filled = int((completed_count / total_probes) * bar_len)
                        filled_bar = "=" * filled
                        empty_bar = "-" * (bar_len - filled)
                        sys.stdout.write(f"\r\033[1;36mProbing models:\033[0m \033[90m[\033[1;32m{filled_bar}\033[90m{empty_bar}]\033[0m \033[1;37m{completed_count}/{total_probes}\033[0m \033[1;33m({pct}%)\033[0m")
                        sys.stdout.flush()


                    return m_obj, ok, latency

                probe_results = await asyncio.gather(*[probe_with_progress(m) for m in valid_models])
                sys.stdout.write("\n")
                sys.stdout.flush()

                accessible_models = []
                for m, ok, latency in probe_results:
                    mid = m.get("id")
                    if ok and mid:
                        self._latencies[mid] = latency
                        accessible_models.append(m)

                accessible_models.sort(key=lambda m: self._latencies.get(m.get("id", ""), 999.0))


                logger.info(
                    f"Probe complete: {len(accessible_models)} working models found (filtered out {len(all_models) - len(accessible_models)} non-working/404)"
                )
                top_3 = accessible_models[:3]
                logger.info("Top-3 Priority Models (Lowest Latency):")
                for rank, m in enumerate(top_3, 1):
                    mid = m.get("id", "")
                    logger.info(f"  {rank}. {mid} ({self._latencies.get(mid, 0.0):.3f}s)")

                for m in accessible_models[3:]:
                    mid = m.get("id", "")
                    logger.info(f"  - Standby Model: {mid} ({self._latencies.get(mid, 0.0):.3f}s)")

                return accessible_models

        except Exception as e:
            logger.error(f"Model discovery failed: {e}, falling back to verified working list")
            return self._load_fallback_models()

    def _load_fallback_models(self) -> list[dict]:
        for path in [
            os.path.join(os.path.dirname(__file__), "config", "models_status.json"),
            os.path.join(os.path.dirname(__file__), "tests", "models_status.json"),
            os.path.join(os.path.dirname(__file__), "models_status.json"),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                    working = data.get("working_models", [])
                    if working:
                        logger.info(f"Loaded {len(working)} working models from {path}")
                        for i, mid in enumerate(working):
                            self._latencies[mid] = 0.3 + (i * 0.05)
                        return [{"id": mid} for mid in working]
                except Exception as e:
                    logger.warning(f"Failed to read {path}: {e}")

        fallback_list = [
            "deepseek-ai/deepseek-v4-flash-0731",
            "deepseek-ai/deepseek-v4-pro-0813",
            "google/diffusiongemma-26b-a4b-it",
            "google/gemma-4-31b-it",
            "meta/llama-3.2-11b-vision-instruct",
            "meta/llama-3.2-90b-vision-instruct",
            "meta/muse-glimmer-30b",
            "minimaxai/minimax-m3",
            "moonshotai/kimi-k3",
            "nvidia/ising-calibration-1.5-31b",
            "nvidia/llama-3.1-nemoguard-8b-content-safety",
            "nvidia/llama-3.1-nemotron-safety-guard-8b-v3",
            "nvidia/nemotron-3-nano-30b-a3b",
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
            "nvidia/nemotron-3-super-120b-a12b",
            "nvidia/nemotron-3.5-content-safety",
            "nvidia/nemotron-3.5-lightning-30b-a3b",
            "nvidia/riva-translate-4b-instruct-v1.1",
            "nvidia/riva-translate-4b-instruct-v2",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "poolside/laguna-xs-2.1",
        ]
        for i, mid in enumerate(fallback_list):
            self._latencies[mid] = 0.3 + (i * 0.05)
        return [{"id": mid} for mid in fallback_list]

    def _is_model_healthy(self, model_id: str) -> bool:
        if model_id not in self._health:
            return True
        record = self._health[model_id]
        now = time.time()
        if now - record.get("last_check", 0) > HEALTH_REFRESH_INTERVAL:
            record["failures"] = 0
            record["last_check"] = now
            record["healthy"] = True
        return record.get("healthy", True)

    def _record_failure(self, model_id: str):
        if model_id not in self._health:
            self._health[model_id] = {"failures": 0, "last_check": 0, "healthy": True}
        self._health[model_id]["failures"] += 1
        self._health[model_id]["last_check"] = time.time()
        if self._health[model_id]["failures"] >= 2:
            self._health[model_id]["healthy"] = False
            logger.warning(f"Model {model_id} temporarily marked unhealthy after {self._health[model_id]['failures']} failures")

    def _record_success(self, model_id: str, elapsed: float):
        if model_id in self._health:
            self._health[model_id]["failures"] = 0
            self._health[model_id]["healthy"] = True

        if model_id in self._latencies:
            self._latencies[model_id] = round(0.7 * self._latencies[model_id] + 0.3 * elapsed, 3)
        else:
            self._latencies[model_id] = round(elapsed, 3)

    def _build_healthy_pool(self) -> list[str]:
        healthy = [
            mid for mid in [m.get("id") for m in self.models if m.get("id")]
            if self._is_model_healthy(mid)
        ]
        healthy.sort(key=lambda mid: self._latencies.get(mid, 999.0))
        return healthy

    async def _route_request(self, request: ChatCompletionRequest) -> Response:
        async with self._lock:
            if not self.models:
                self.models = await self._discover_models()
                if not self.models:
                    raise RuntimeError("No models available from NVIDIA API")

            now = time.time()
            if not self._healthy_pool or (now - self._pool_updated) > CACHE_TTL:
                self._healthy_pool = self._build_healthy_pool()
                self._pool_updated = now
                logger.info(f"Healthy pool updated: {len(self._healthy_pool)} models")

            is_vision = self._is_vision_request(request)
            requested_model = request.model
            if requested_model and requested_model.lower() not in ("nim-free", "nim_free", "auto"):
                candidate_ids = [requested_model]
                if is_vision and not self._is_vision_model(requested_model):
                    vision_fallbacks = [
                        mid for mid in self._healthy_pool
                        if self._is_vision_model(mid)
                    ]
                    candidate_ids += vision_fallbacks
            else:
                pool = self._healthy_pool if self._healthy_pool else [m.get("id") for m in self.models if m.get("id")]
                candidate_pool = pool if pool else []

                if is_vision:
                    vision_capable = [
                        mid for mid in candidate_pool
                        if self._is_vision_model(mid)
                    ]
                    if not vision_capable:
                        raise HTTPException(
                            status_code=400,
                            detail="Image/multimodal input detected in request, but no vision-capable models are currently available in the active pool."
                        )
                    candidate_pool = vision_capable
                    logger.info(f"Vision request detected: isolated pool to {len(candidate_pool)} vision models: {candidate_pool}")

                if request.tools:
                    tool_incompatible = ["safety", "guard", "translate", "ising-calibration", "topic-control"]
                    tool_capable = [
                        mid for mid in candidate_pool
                        if not any(k in mid.lower() for k in tool_incompatible)
                    ]
                    if tool_capable:
                        candidate_pool = tool_capable

                if not candidate_pool:
                    raise RuntimeError("No model IDs available in pool")

                candidate_pool.sort(key=lambda mid: self._latencies.get(mid, 999.0))

                top_3_pool = candidate_pool[:3]
                standby_pool = candidate_pool[3:]

                start_idx = self.model_index % len(top_3_pool)
                self.model_index = (self.model_index + 1) % len(top_3_pool)

                ordered_top_3 = [top_3_pool[(start_idx + i) % len(top_3_pool)] for i in range(len(top_3_pool))]
                candidate_ids = ordered_top_3 + standby_pool

        tried_models = set()
        attempts = min(FAILOVER_MAX_ATTEMPTS, len(candidate_ids))
        for i in range(attempts):
            selected_id = candidate_ids[i]

            if selected_id in tried_models:
                continue
            tried_models.add(selected_id)

            current_latency = self._latencies.get(selected_id, 0.0)
            logger.info(f"Routing request (attempt {i+1}/{attempts}) -> {selected_id} (latency: {current_latency:.3f}s, stream={request.stream})")

            t0 = time.time()
            try:
                response = await self._call_nvidia_endpoint(selected_id, request)
                elapsed = time.time() - t0
                self._record_success(selected_id, elapsed)
                return response
            except HTTPException as e:
                if e.status_code in (400, 422, 429, 500, 502, 503, 504):
                    self._record_failure(selected_id)
                    logger.warning(f"Model {selected_id} failed with status {e.status_code} ({e.detail}), failing over...")
                elif e.status_code == 404:
                    logger.warning(f"Model {selected_id} returned 404, skipping...")
                else:
                    logger.error(f"Non-retryable error for {selected_id}: {e.status_code} - {e.detail}")
                    raise
            except Exception as e:
                self._record_failure(selected_id)
                logger.error(f"Unexpected error calling {selected_id}: {e}")

        raise RuntimeError(f"All {attempts} model attempts failed for request")


    async def _call_nvidia_endpoint(self, model_id: str, request: ChatCompletionRequest) -> Response:
        url = f"{NIM_API_BASE}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        sanitized_messages = []
        for msg in request.messages:
            m = dict(msg)
            role = m.get("role", "")
            content = m.get("content")

            if content is None or (isinstance(content, str) and not content.strip()) or content == []:
                if m.get("reasoning_content"):
                    m["content"] = str(m["reasoning_content"]).strip()
                elif m.get("reasoning"):
                    m["content"] = str(m["reasoning"]).strip()
                elif m.get("tool_calls"):
                    m["content"] = " "
                else:
                    m["content"] = "..." if role == "assistant" else " "
            sanitized_messages.append(m)

        payload = {
            "model": model_id,
            "messages": sanitized_messages,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": bool(request.stream),
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.stop is not None:
            payload["stop"] = request.stop
        if request.tools is not None:
            payload["tools"] = request.tools

        client = httpx.AsyncClient(timeout=90.0)

        if request.stream:
            try:
                req = client.build_request("POST", url, headers=headers, json=payload)
                response = await client.send(req, stream=True)

                if response.status_code == 200:
                    async def stream_generator():
                        try:
                            async for chunk in response.aiter_raw():
                                yield chunk
                        finally:
                            await response.aclose()
                            await client.aclose()

                    return StreamingResponse(
                        stream_generator(),
                        status_code=200,
                        media_type="text/event-stream",
                        headers={
                            "Cache-Control": "no-cache",
                            "Connection": "keep-alive",
                            "X-Accel-Buffering": "no"
                        }
                    )
                else:
                    body = await response.aread()
                    await response.aclose()
                    await client.aclose()
                    try:
                        err_data = json.loads(body.decode())
                        detail = err_data.get("error", {}).get("message", str(err_data))
                    except Exception:
                        detail = body.decode()
                    raise HTTPException(status_code=response.status_code, detail=detail)
            except HTTPException:
                raise
            except Exception as e:
                await client.aclose()
                raise HTTPException(status_code=502, detail=str(e))
        else:
            try:
                response = await client.post(url, headers=headers, json=payload)

                if response.status_code == 200:
                    try:
                        resp_json = response.json()
                        choices = resp_json.get("choices", [])
                        modified = False
                        for c in choices:
                            msg_obj = c.get("message", {})
                            if msg_obj.get("role") == "assistant" and (msg_obj.get("content") is None or msg_obj.get("content") == ""):
                                fallback = msg_obj.get("reasoning_content") or msg_obj.get("reasoning")
                                if fallback:
                                    msg_obj["content"] = str(fallback).strip()
                                    modified = True
                                elif not msg_obj.get("tool_calls"):
                                    msg_obj["content"] = " "
                                    modified = True
                        if modified:
                            return Response(content=json.dumps(resp_json), media_type="application/json", status_code=200)
                    except Exception as e:
                        logger.debug(f"Response normalization error: {e}")

                    return Response(content=response.text, media_type="application/json", status_code=200)
                elif response.status_code in (429, 500, 502, 503, 504):
                    raise HTTPException(status_code=response.status_code, detail=f"NVIDIA API error: {response.status_code}")
                elif response.status_code == 404:
                    raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
                else:
                    try:
                        err_data = response.json()
                        detail = err_data.get("error", {}).get("message", str(err_data))
                    except Exception:
                        detail = response.text
                    raise HTTPException(status_code=response.status_code, detail=detail)
            except httpx.RequestError as e:
                logger.error(f"Request error calling NVIDIA API for {model_id}: {e}")
                raise HTTPException(status_code=502, detail=str(e))
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to call NVIDIA API for {model_id}: {e}")
                raise HTTPException(status_code=502, detail=str(e))
            finally:
                await client.aclose()

    async def handle_request(self, request: Request) -> Response:
        try:
            body = await request.json()
            chat_req = ChatCompletionRequest(**body)
            return await self._route_request(chat_req)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            raise HTTPException(status_code=500, detail=str(e))


_router_instance: Optional[ModelRouter] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _router_instance
    api_key = os.getenv("NVIDIA_API_KEY", "")
    if not api_key:
        logger.warning("NVIDIA_API_KEY not set in environment (.env)")
    _router_instance = ModelRouter(api_key=api_key)
    _router_instance.models = await _router_instance._discover_models()
    _router_instance._healthy_pool = _router_instance._build_healthy_pool()
    logger.info(f"nim-router started with {len(_router_instance.models)} working models in active pool")
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

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 11435))
    uvicorn.run(create_app(), host="0.0.0.0", port=port, log_level="info")