import asyncio
import json
import time
from fastapi import HTTPException, Request, Response
import httpx

from nim_router.config import (
    CACHE_TTL,
    HEALTH_REFRESH_INTERVAL,
    MODEL_MAX_CONCURRENCY,
    MODEL_MAX_RPM,
    PRIMARY_POOL_SIZE,
    RATE_LIMIT_COOLDOWN,
    NIM_API_BASE,
    OPENROUTER_API_BASE,
    OPENCODE_API_BASE,
    get_primary_model,
)
from nim_router.logger import logger
from nim_router.schemas import ChatCompletionRequest
from nim_router.catalog import is_banned_model, load_fallback_models
from nim_router.classifier import is_vision_model, is_vision_request
from nim_router.client import probe_model, discover_models, call_provider_endpoint, call_nvidia_endpoint

class ModelRouter:
    def __init__(self, api_key: str | list[str], openrouter_key: str = "", opencode_key: str = ""):
        if isinstance(api_key, list):
            self.api_keys = [k.strip() for k in api_key if k.strip()]
        else:
            self.api_keys = [k.strip() for k in (api_key or "").split(",") if k.strip()]
        if not self.api_keys:
            self.api_keys = [""]
        self.api_key = self.api_keys[0]
        self.openrouter_key = openrouter_key.strip()
        self.opencode_key = opencode_key.strip()
        self.key_index = 0
        self.models: list[dict] = []
        self.model_index = 0
        self._lock = asyncio.Lock()
        self._health: dict[str, dict] = {}
        self._latencies: dict[str, float] = {}
        self._rate_limited_until: dict[str, float] = {}
        self._request_history: dict[str, list[float]] = {}
        self._in_flight: dict[str, int] = {}
        self._healthy_pool: list[str] = []
        self._pool_updated: float = 0

    def _get_next_api_key(self) -> str:
        key = self.api_keys[self.key_index % len(self.api_keys)]
        self.key_index = (self.key_index + 1) % len(self.api_keys)
        return key

    def _get_provider_info(self, model_id: str) -> tuple[str, str, list[str]]:
        mid = model_id.lower()
        if mid.endswith(":free") or "openrouter/" in mid or mid.startswith("openrouter"):
            return OPENROUTER_API_BASE, self.openrouter_key, [self.openrouter_key] if self.openrouter_key else [""]
        elif mid.startswith("opencode/") or "opencode" in mid:
            return OPENCODE_API_BASE, self.opencode_key, [self.opencode_key] if self.opencode_key else [""]
        else:
            return NIM_API_BASE, self._get_next_api_key(), self.api_keys

    def _get_recent_rpm(self, model_id: str, now: float) -> int:
        cutoff = now - 60.0
        history = [t for t in self._request_history.get(model_id, []) if t > cutoff]
        self._request_history[model_id] = history
        return len(history)

    def _record_request_dispatch(self, model_id: str, now: float):
        self._request_history.setdefault(model_id, []).append(now)

    def _is_banned_model(self, model_id: str) -> bool:
        return is_banned_model(model_id)

    def _is_vision_model(self, model_id: str) -> bool:
        return is_vision_model(model_id)

    def _is_vision_request(self, request: ChatCompletionRequest) -> bool:
        return is_vision_request(request)

    async def _probe_model(self, client: httpx.AsyncClient, model_id: str, sem: asyncio.Semaphore) -> tuple[bool, float]:
        base_url, key, _ = self._get_provider_info(model_id)
        return await probe_model(key, client, model_id, sem, base_url)

    async def _discover_models(self) -> list[dict]:
        return await discover_models(self.api_keys, self._latencies, self.openrouter_key, self.opencode_key)

    def _load_fallback_models(self) -> list[dict]:
        return load_fallback_models(self._latencies)

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
        if status_code in (429, 402):
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
            rpm_over = 1 if self._get_recent_rpm(mid, now) >= MODEL_MAX_RPM else 0
            busy = 1 if self._in_flight.get(mid, 0) >= MODEL_MAX_CONCURRENCY else 0
            in_flight_count = self._in_flight.get(mid, 0)
            latency = self._latencies.get(mid, 999.0)
            return (throttled, rpm_over, busy, in_flight_count, latency)

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

            target_model = requested_model if (requested_model and requested_model.lower() not in ("nim-free", "nim_free", "auto")) else get_primary_model()

            if target_model and target_model.lower() not in ("nim-free", "nim_free", "auto"):
                if self._is_banned_model(target_model):
                    logger.warning(f"Target model {target_model} is banned/non-chat; routing to healthy pool.")
                    candidate_ids = candidate_pool
                else:
                    other_candidates = [mid for mid in candidate_pool if mid != target_model]
                    candidate_ids = [target_model] + other_candidates
            else:
                candidate_pool.sort(key=lambda mid: (
                    1 if self._rate_limited_until.get(mid, 0) > now else 0,
                    1 if self._get_recent_rpm(mid, now) >= MODEL_MAX_RPM else 0,
                    1 if self._in_flight.get(mid, 0) >= MODEL_MAX_CONCURRENCY else 0,
                    self._in_flight.get(mid, 0),
                    self._latencies.get(mid, 999.0)
                ))
                top_size = min(PRIMARY_POOL_SIZE, len(candidate_pool))
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
            current_rpm = self._get_recent_rpm(selected_id, time.time())
            in_flight_num = self._in_flight.get(selected_id, 0)
            logger.info(f"Routing request (attempt {len(tried_models)}/{attempts}) -> {selected_id} (latency: {current_latency:.3f}s, rpm: {current_rpm}/{MODEL_MAX_RPM}, in-flight: {in_flight_num}, stream={request.stream})")

            t0 = time.time()
            self._record_request_dispatch(selected_id, t0)
            self._in_flight[selected_id] = in_flight_num + 1
            try:
                base_url, _, keys_to_try = self._get_provider_info(selected_id)
                for k_idx, current_key in enumerate(keys_to_try):
                    try:
                        response = await call_provider_endpoint(current_key, selected_id, request, base_url)
                        elapsed = time.time() - t0
                        self._record_success(selected_id, elapsed)
                        logger.success(f"Request completed successfully via {selected_id} ({elapsed:.3f}s)")
                        return response
                    except HTTPException as e:
                        if e.status_code == 429 and k_idx < len(keys_to_try) - 1:
                            logger.warning(f"Model {selected_id} rate limited on key {current_key[:8]}..., retrying with next API key...")
                            await asyncio.sleep(0.1)
                            continue
                        raise
            except HTTPException as e:
                last_error = e
                self._record_failure(selected_id, status_code=e.status_code)
                if e.status_code in (429, 402):
                    logger.warning(f"Model {selected_id} returned status {e.status_code} (Rate Limited/Billing), backing off and failing over...")
                    await asyncio.sleep(0.15)
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
            finally:
                self._in_flight[selected_id] = max(0, self._in_flight.get(selected_id, 1) - 1)

        detail_msg = last_error.detail if isinstance(last_error, HTTPException) else str(last_error)
        raise HTTPException(
            status_code=503,
            detail=f"All {len(tried_models)} candidate NIM models failed or are temporarily rate-limited. Last error: {detail_msg}"
        )

    async def _call_nvidia_endpoint(self, model_id: str, request: ChatCompletionRequest, api_key: str = None) -> Response:
        base_url, key, _ = self._get_provider_info(model_id)
        selected_key = api_key or key
        return await call_provider_endpoint(selected_key, model_id, request, base_url)

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
