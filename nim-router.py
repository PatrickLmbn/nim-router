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

SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")

def log_success(self, message, *args, **kws):
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(SUCCESS_LEVEL, message, args, **kws)

logging.Logger.success = log_success

class ColoredFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: "\033[90m",
        logging.INFO: "\033[94m",
        SUCCESS_LEVEL: "\033[92m",
        logging.WARNING: "\033[93m",
        logging.ERROR: "\033[91m",
        logging.CRITICAL: "\033[1;91m",
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, "")
        reset = "\033[0m"
        asctime = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        levelname = record.levelname
        msg = record.getMessage()
        return f"{asctime} - {color}{levelname}{reset} - {color}{msg}{reset}"

log_handler = logging.StreamHandler(sys.stdout)
log_handler.setFormatter(ColoredFormatter())
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("nim-router")
logger.setLevel(logging.INFO)
logger.handlers = [log_handler]
logger.propagate = False

NIM_API_BASE = "https://integrate.api.nvidia.com/v1"
HEALTH_REFRESH_INTERVAL = 180
RATE_LIMIT_COOLDOWN = 20
CACHE_TTL = 180

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
        self._rate_limited_until: dict[str, float] = {}
        self._healthy_pool: list[str] = []
        self._pool_updated: float = 0

    def _is_banned_model(self, model_id: str) -> bool:
        if not model_id:
            return True
        mid = model_id.lower().strip()
        if mid in BANNED_MODELS:
            return True
        return any(k in mid for k in BANNED_KEYWORDS)

    def _is_vision_model(self, model_id: str) -> bool:
        if self._is_banned_model(model_id):
            return False
        mid = model_id.lower().strip()
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
        if self._is_banned_model(model_id):
            return False, 999.0
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
                if resp.status_code == 200:
                    return True, elapsed
                elif resp.status_code == 429:
                    return True, 10.0 + elapsed
                else:
                    return False, 999.0
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
                logger.info(f"Discovered {len(all_models)} total models from NVIDIA API. Filtering non-chat/banned models...")

                sem = asyncio.Semaphore(10)
                valid_models = [
                    m for m in all_models
                    if m.get("id") and not self._is_banned_model(m.get("id"))
                ]
                total_probes = len(valid_models)
                completed_count = 0
                lock = asyncio.Lock()

                async def probe_with_progress(m_obj):
                    nonlocal completed_count
                    mid = m_obj.get("id", "")
                    ok, latency = await self._probe_model(client, mid, sem)
                    async with lock:
                        completed_count += 1
                        pct = int((completed_count / total_probes) * 100) if total_probes else 100
                        bar_len = 30
                        filled = int((completed_count / total_probes) * bar_len) if total_probes else bar_len
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

                logger.success(
                    f"Probe complete: {len(accessible_models)} working chat models found (filtered out non-working & banned models)"
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
                    working = [mid for mid in data.get("working_models", []) if not self._is_banned_model(mid)]
                    if working:
                        logger.info(f"Loaded {len(working)} working models from {path}")
                        for i, mid in enumerate(working):
                            self._latencies[mid] = 0.3 + (i * 0.05)
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
            "moonshotai/kimi-k3",
            "deepseek-ai/deepseek-v4-flash-0731",
            "deepseek-ai/deepseek-v4-pro-0813",
            "poolside/laguna-xs-2.1",
        ]
        clean_fallback = [mid for mid in fallback_list if not self._is_banned_model(mid)]
        for i, mid in enumerate(clean_fallback):
            self._latencies[mid] = 0.3 + (i * 0.05)
        return [{"id": mid} for mid in clean_fallback]

    def _is_model_healthy(self, model_id: str) -> bool:
        if self._is_banned_model(model_id):
            return False
        if model_id not in self._health:
            return True
        record = self._health[model_id]
        now = time.time()
        if now - record.get("last_check", 0) > HEALTH_REFRESH_INTERVAL:
            record["failures"] = 0
            record["last_check"] = now
            record["healthy"] = True
        return record.get("healthy", True)

    def _record_failure(self, model_id: str, status_code: int = 500):
        now = time.time()
        if status_code == 429:
            self._rate_limited_until[model_id] = now + RATE_LIMIT_COOLDOWN
            current = self._latencies.get(model_id, 1.0)
            self._latencies[model_id] = round(current + 2.5, 3)
        elif status_code == 404:
            self.models = [m for m in self.models if m.get("id") != model_id]
            self._healthy_pool = [mid for mid in self._healthy_pool if mid != model_id]
            return

        if model_id not in self._health:
            self._health[model_id] = {"failures": 0, "last_check": 0, "healthy": True}
        self._health[model_id]["failures"] += 1
        self._health[model_id]["last_check"] = now
        if self._health[model_id]["failures"] >= 3:
            self._health[model_id]["healthy"] = False
            logger.warning(f"Model {model_id} temporarily marked unhealthy after {self._health[model_id]['failures']} failures")

    def _record_success(self, model_id: str, elapsed: float):
        if model_id in self._health:
            self._health[model_id]["failures"] = 0
            self._health[model_id]["healthy"] = True
        self._rate_limited_until.pop(model_id, None)

        if model_id in self._latencies:
            self._latencies[model_id] = round(0.7 * self._latencies[model_id] + 0.3 * elapsed, 3)
        else:
            self._latencies[model_id] = round(elapsed, 3)

    def _build_healthy_pool(self) -> list[str]:
        now = time.time()
        all_ids = [m.get("id") for m in self.models if m.get("id") and not self._is_banned_model(m.get("id"))]
        healthy = [mid for mid in all_ids if self._is_model_healthy(mid)]

        if not healthy and all_ids:
            logger.warning("All models in pool were marked unhealthy; auto-resetting health states to restore availability.")
            self._health.clear()
            self._rate_limited_until.clear()
            healthy = list(all_ids)

        def sort_key(mid: str):
            throttled = 1 if self._rate_limited_until.get(mid, 0) > now else 0
            return (throttled, self._latencies.get(mid, 999.0))

        healthy.sort(key=sort_key)
        return healthy

    async def _route_request(self, request: ChatCompletionRequest) -> Response:
        async with self._lock:
            if not self.models:
                self.models = await self._discover_models()
                if not self.models:
                    self.models = self._load_fallback_models()

            now = time.time()
            if not self._healthy_pool or (now - self._pool_updated) > CACHE_TTL:
                self._healthy_pool = self._build_healthy_pool()
                self._pool_updated = now
                logger.info(f"Healthy pool updated: {len(self._healthy_pool)} models")

            is_vision = self._is_vision_request(request)
            requested_model = request.model

            pool = self._healthy_pool if self._healthy_pool else [m.get("id") for m in self.models if m.get("id") and not self._is_banned_model(m.get("id"))]
            candidate_pool = [mid for mid in pool if not self._is_banned_model(mid)]

            if not candidate_pool:
                self._health.clear()
                self._rate_limited_until.clear()
                candidate_pool = self._build_healthy_pool()

            if is_vision:
                vision_capable = [
                    mid for mid in candidate_pool
                    if self._is_vision_model(mid)
                ]
                if not vision_capable:
                    vision_capable = [
                        m.get("id") for m in self.models
                        if m.get("id") and self._is_vision_model(m.get("id"))
                    ]
                if not vision_capable:
                    raise HTTPException(
                        status_code=400,
                        detail="Image/multimodal input detected in request, but no vision-capable models are available."
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

            if requested_model and requested_model.lower() not in ("nim-free", "nim_free", "auto"):
                if self._is_banned_model(requested_model):
                    logger.warning(f"Requested model {requested_model} is banned/non-chat; routing to healthy pool.")
                    candidate_ids = candidate_pool
                else:
                    other_candidates = [mid for mid in candidate_pool if mid != requested_model]
                    candidate_ids = [requested_model] + other_candidates
            else:
                candidate_pool.sort(key=lambda mid: (
                    1 if self._rate_limited_until.get(mid, 0) > now else 0,
                    self._latencies.get(mid, 999.0)
                ))
                top_size = min(3, len(candidate_pool))
                if top_size > 0:
                    top_pool = candidate_pool[:top_size]
                    standby_pool = candidate_pool[top_size:]
                    start_idx = self.model_index % len(top_pool)
                    self.model_index = (self.model_index + 1) % len(top_pool)
                    ordered_top = [top_pool[(start_idx + i) % len(top_pool)] for i in range(len(top_pool))]
                    candidate_ids = ordered_top + standby_pool
                else:
                    candidate_ids = candidate_pool

        tried_models = set()
        last_error = None
        attempts = len(candidate_ids)

        for selected_id in candidate_ids:
            if selected_id in tried_models:
                continue
            tried_models.add(selected_id)

            current_latency = self._latencies.get(selected_id, 0.0)
            logger.info(f"Routing request (attempt {len(tried_models)}/{attempts}) -> {selected_id} (latency: {current_latency:.3f}s, stream={request.stream})")

            t0 = time.time()
            try:
                response = await self._call_nvidia_endpoint(selected_id, request)
                elapsed = time.time() - t0
                self._record_success(selected_id, elapsed)
                logger.success(f"Request completed successfully via {selected_id} ({elapsed:.3f}s)")
                return response
            except HTTPException as e:
                last_error = e
                self._record_failure(selected_id, status_code=e.status_code)
                if e.status_code == 429:
                    logger.warning(f"Model {selected_id} returned 429 (Rate Limited), backing off 0.1s and failing over...")
                    await asyncio.sleep(0.1)
                elif e.status_code in (400, 422, 500, 502, 503, 504):
                    logger.warning(f"Model {selected_id} failed with status {e.status_code} ({e.detail}), failing over...")
                elif e.status_code == 404:
                    logger.warning(f"Model {selected_id} returned 404 Not Found, removed from pool.")
                else:
                    logger.error(f"Non-retryable error for {selected_id}: {e.status_code} - {e.detail}")
                    raise
            except Exception as e:
                last_error = e
                self._record_failure(selected_id, status_code=500)
                logger.error(f"Unexpected error calling {selected_id}: {e}")

        detail_msg = last_error.detail if isinstance(last_error, HTTPException) else str(last_error)
        raise HTTPException(
            status_code=503,
            detail=f"All {len(tried_models)} candidate NIM models failed or are temporarily rate-limited. Last error: {detail_msg}"
        )

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
        except HTTPException as e:
            return Response(
                content=json.dumps({
                    "error": {
                        "message": e.detail,
                        "type": "upstream_error",
                        "code": e.status_code
                    }
                }),
                status_code=e.status_code,
                media_type="application/json"
            )
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            return Response(
                content=json.dumps({
                    "error": {
                        "message": str(e),
                        "type": "router_error",
                        "code": 500
                    }
                }),
                status_code=500,
                media_type="application/json"
            )


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

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 11435))
    uvicorn.run(create_app(), host="0.0.0.0", port=port, log_level="info")