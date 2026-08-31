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
    MAX_LATENCY_THRESHOLD,
    NIM_API_BASE,
    OPENROUTER_API_BASE,
    OPENCODE_API_BASE,
    GROQ_API_BASE,
    CEREBRAS_API_BASE,
    get_primary_model,
)
from nim_router.logger import logger
from nim_router.schemas import ChatCompletionRequest
from nim_router.catalog import is_banned_model, load_fallback_models
from nim_router.classifier import (
    is_vision_model,
    is_coding_model,
    is_reasoning_model,
    is_moe_model,
    is_chat_model,
    is_vision_request,
    estimate_token_count,
)
from nim_router.client import probe_model, discover_models, call_provider_endpoint, call_nvidia_endpoint

class ModelRouter:
    def __init__(self, api_key: str | list[str], openrouter_key: str = "", opencode_key: str = "", groq_keys: str | list[str] = "", cerebras_keys: str | list[str] = ""):
        if isinstance(api_key, list):
            self.api_keys = [k.strip() for k in api_key if k.strip()]
        else:
            self.api_keys = [k.strip() for k in (api_key or "").split(",") if k.strip()]
        if not self.api_keys:
            self.api_keys = [""]
        self.api_key = self.api_keys[0]

        self.openrouter_key = openrouter_key.strip()
        self.opencode_key = opencode_key.strip()

        if isinstance(groq_keys, list):
            self.groq_keys = [k.strip() for k in groq_keys if k.strip()]
        else:
            self.groq_keys = [k.strip() for k in (groq_keys or "").split(",") if k.strip()]

        if isinstance(cerebras_keys, list):
            self.cerebras_keys = [k.strip() for k in cerebras_keys if k.strip()]
        else:
            self.cerebras_keys = [k.strip() for k in (cerebras_keys or "").split(",") if k.strip()]

        self.key_index = 0
        self.groq_key_index = 0
        self.cerebras_key_index = 0
        self.models: list[dict] = []
        self.model_index = 0
        self._lock = asyncio.Lock()
        self._health: dict[str, dict] = {}
        self._latencies: dict[str, float] = {}
        self._tps: dict[str, float] = {}
        self._reliability: dict[str, float] = {}
        self._rate_limited_until: dict[str, float] = {}
        self._request_history: dict[str, list[float]] = {}
        self._in_flight: dict[str, int] = {}
        self._healthy_pool: list[str] = []
        self._pool_updated: float = 0
        self._model_providers: dict[str, str] = {}

    def _get_next_api_key(self) -> str:
        key = self.api_keys[self.key_index % len(self.api_keys)]
        self.key_index = (self.key_index + 1) % len(self.api_keys)
        return key

    def _get_provider_name(self, model_id: str) -> str:
        mid_clean = model_id
        for prefix in ("[NVIDIA] ", "[OpenRouter] ", "[OpenCode] ", "[Groq] ", "[Cerebras] ", "[Category] "):
            if mid_clean.startswith(prefix):
                mid_clean = mid_clean[len(prefix):].strip()

        if mid_clean in self._model_providers:
            return self._model_providers[mid_clean]
        mid = mid_clean.lower()
        if mid.endswith(":free") or "openrouter/" in mid or mid.startswith("openrouter"):
            return "OpenRouter"
        elif mid.startswith("opencode/") or "opencode" in mid or mid.endswith("-free"):
            return "OpenCode"
        elif any(k in mid for k in ("llama3-", "mixtral-8x7b", "gemma2-", "groq", "versatile", "instant", "specdec", "orpheus", "allam", "compound")):
            return "Groq"
        elif "cerebras" in mid or "llama3.1" in mid or "csk" in mid:
            return "Cerebras"
        else:
            return "NVIDIA"

    def _get_provider_info(self, model_id: str) -> tuple[str, str, list[str]]:
        provider = self._get_provider_name(model_id)
        if provider == "OpenRouter":
            return OPENROUTER_API_BASE, self.openrouter_key, [self.openrouter_key] if self.openrouter_key else [""]
        elif provider == "OpenCode":
            return OPENCODE_API_BASE, self.opencode_key, [self.opencode_key] if self.opencode_key else [""]
        elif provider == "Groq":
            keys = self.groq_keys if self.groq_keys else [""]
            rotated = keys[self.groq_key_index:] + keys[:self.groq_key_index]
            self.groq_key_index = (self.groq_key_index + 1) % len(keys)
            return GROQ_API_BASE, rotated[0], rotated
        elif provider == "Cerebras":
            keys = self.cerebras_keys if self.cerebras_keys else [""]
            rotated = keys[self.cerebras_key_index:] + keys[:self.cerebras_key_index]
            self.cerebras_key_index = (self.cerebras_key_index + 1) % len(keys)
            return CEREBRAS_API_BASE, rotated[0], rotated
        else:
            rotated_keys = self.api_keys[self.key_index:] + self.api_keys[:self.key_index]
            self.key_index = (self.key_index + 1) % len(self.api_keys)
            return NIM_API_BASE, rotated_keys[0], rotated_keys

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
        discovered = await discover_models(
            self.api_keys,
            self._latencies,
            self.openrouter_key,
            self.opencode_key,
            self.groq_keys,
            self.cerebras_keys
        )
        for m in discovered:
            mid = m.get("id")
            if mid and "provider" in m:
                self._model_providers[mid] = m["provider"]
        return discovered

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
        cur_rel = self._reliability.get(model_id, 1.0)
        self._reliability[model_id] = max(0.05, 0.7 * cur_rel)

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

    def _record_success(self, model_id: str, elapsed: float, token_count: int = 0):
        if model_id in self._health:
            self._health[model_id]["failures"] = 0
            self._health[model_id]["healthy"] = True
        self._rate_limited_until.pop(model_id, None)

        cur_rel = self._reliability.get(model_id, 1.0)
        self._reliability[model_id] = min(1.0, 0.85 * cur_rel + 0.15)

        if model_id in self._latencies:
            self._latencies[model_id] = round(0.7 * self._latencies[model_id] + 0.3 * elapsed, 3)
        else:
            self._latencies[model_id] = round(elapsed, 3)

        if token_count > 0 and elapsed > 0.05:
            measured_tps = token_count / elapsed
            cur_tps = self._tps.get(model_id, 40.0)
            self._tps[model_id] = round(0.7 * cur_tps + 0.3 * measured_tps, 2)

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

            lat = self._latencies.get(mid, 1.0)
            rel = self._reliability.get(mid, 1.0)
            tps = self._tps.get(mid, 40.0)
            perf_score = (1.0 / max(0.01, lat)) * (rel ** 2) * (1.0 + 0.01 * tps)

            return (throttled, rpm_over, busy, in_flight_count, -perf_score)

        healthy.sort(key=sort_key)
        return healthy

    async def initialize(self):
        async with self._lock:
            self.models = self._load_fallback_models()
            for m in self.models:
                mid = m.get("id")
                if mid:
                    self._model_providers[mid] = self._get_provider_name(mid)
            self._healthy_pool = self._build_healthy_pool()
            self._pool_updated = time.time()

            nvidia_count = sum(1 for m in self.models if self._get_provider_name(m.get("id", "")) == "NVIDIA")
            or_count = sum(1 for m in self.models if self._get_provider_name(m.get("id", "")) == "OpenRouter")
            oc_count = sum(1 for m in self.models if self._get_provider_name(m.get("id", "")) == "OpenCode")
            groq_count = sum(1 for m in self.models if self._get_provider_name(m.get("id", "")) == "Groq")
            cerebras_count = sum(1 for m in self.models if self._get_provider_name(m.get("id", "")) == "Cerebras")

            logger.success(
                f"nim-router initialized instantly with {len(self._healthy_pool)} working models in pool "
                f"(NVIDIA: {nvidia_count}, OpenRouter: {or_count}, OpenCode: {oc_count}, Groq: {groq_count}, Cerebras: {cerebras_count})"
            )
        asyncio.create_task(self.refresh_models())

    async def refresh_models(self):
        logger.info("Refreshing model catalog and latency probes across providers in background...")
        new_models = await self._discover_models()
        if new_models:
            async with self._lock:
                self.models = new_models
                for m in self.models:
                    mid = m.get("id")
                    if mid and "provider" in m:
                        self._model_providers[mid] = m["provider"]
                self._healthy_pool = self._build_healthy_pool()
                self._pool_updated = time.time()
                logger.success(f"Refreshed pool: {len(self._healthy_pool)} active models available.")

    async def handle_request(self, raw_request: Request) -> Response:
        try:
            body = await raw_request.json()
            chat_req = ChatCompletionRequest(**body)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid chat completions JSON payload: {e}")
        return await self._route_request(chat_req, raw_request)

    async def route_request(self, chat_req: ChatCompletionRequest, raw_request: Request = None) -> Response:
        return await self._route_request(chat_req, raw_request)

    async def _route_request(self, request: ChatCompletionRequest, raw_request: Request = None) -> Response:
        now = time.time()
        async with self._lock:
            if not self.models:
                self.models = self._load_fallback_models()
                for m in self.models:
                    mid = m.get("id")
                    if mid:
                        self._model_providers[mid] = self._get_provider_name(mid)
                self._healthy_pool = self._build_healthy_pool()
                self._pool_updated = time.time()

            if now - self._pool_updated > HEALTH_REFRESH_INTERVAL:
                self._pool_updated = now
                asyncio.create_task(self.refresh_models())

            requested_model = (request.model or "").strip()
            for prefix in ("[NVIDIA] ", "[OpenRouter] ", "[OpenCode] ", "[Groq] ", "[Cerebras] ", "[Category] "):
                if requested_model.startswith(prefix):
                    requested_model = requested_model[len(prefix):].strip()

            req_lower = requested_model.lower()
            category_target = None
            if req_lower in ("nim-coding", "coding", "code"):
                category_target = "coding"
            elif req_lower in ("nim-reasoning", "reasoning", "reason"):
                category_target = "reasoning"
            elif req_lower in ("nim-vision", "vision", "multimodal"):
                category_target = "vision"
            elif req_lower in ("nim-moe", "moe", "mixture-of-experts"):
                category_target = "moe"
            elif req_lower in ("nim-chat", "chat", "conversation"):
                category_target = "chat"

            candidate_pool = list(self._healthy_pool)
            if not candidate_pool:
                self.models = self._load_fallback_models()
                for m in self.models:
                    mid = m.get("id")
                    if mid:
                        self._model_providers[mid] = self._get_provider_name(mid)
                candidate_pool = [m.get("id") for m in self.models if m.get("id")]

            is_vision = self._is_vision_request(request)

            if is_vision:
                vision_capable = [mid for mid in candidate_pool if self._is_vision_model(mid)]
                if not vision_capable:
                    all_ids = [m.get("id") for m in self.models if m.get("id")]
                    vision_capable = [mid for mid in all_ids if self._is_vision_model(mid)]
                if vision_capable:
                    other_candidates = [mid for mid in candidate_pool if mid not in vision_capable]
                    candidate_pool = vision_capable + other_candidates
                    logger.info(f"Vision payload detected: overriding target to {len(vision_capable)} vision-capable models first.")
                target_model = "nim-free"
            elif category_target:
                if category_target == "coding":
                    cat_filtered = [mid for mid in candidate_pool if is_coding_model(mid)]
                elif category_target == "reasoning":
                    cat_filtered = [mid for mid in candidate_pool if is_reasoning_model(mid)]
                elif category_target == "vision":
                    cat_filtered = [mid for mid in candidate_pool if is_vision_model(mid)]
                elif category_target == "moe":
                    cat_filtered = [mid for mid in candidate_pool if is_moe_model(mid)]
                elif category_target == "chat":
                    cat_filtered = [mid for mid in candidate_pool if is_chat_model(mid)]
                else:
                    cat_filtered = candidate_pool

                if cat_filtered:
                    other_candidates = [mid for mid in candidate_pool if mid not in cat_filtered]
                    candidate_pool = cat_filtered + other_candidates
                    logger.info(f"Purpose category '{category_target}' selected: prioritized {len(cat_filtered)} {category_target} models first.")
                target_model = "nim-free"
            else:
                target_model = requested_model if (requested_model and requested_model.lower() not in ("nim-free", "nim_free", "auto")) else get_primary_model()

            if target_model and target_model.lower() not in ("nim-free", "nim_free", "auto") and not is_vision:
                request.model = target_model
                if self._is_banned_model(target_model):
                    logger.warning(f"Target model {target_model} is banned/non-chat; routing to healthy pool.")
                    candidate_ids = candidate_pool
                else:
                    other_candidates = [mid for mid in candidate_pool if mid != target_model]
                    candidate_ids = [target_model] + other_candidates
            else:
                if candidate_pool:
                    fast_candidates = [mid for mid in candidate_pool if self._latencies.get(mid, 0.0) <= MAX_LATENCY_THRESHOLD]
                    if fast_candidates:
                        non_fast = [mid for mid in candidate_pool if mid not in fast_candidates]
                        candidate_pool = fast_candidates + non_fast

                est_tokens = estimate_token_count(request)

                if est_tokens > 16000:
                    large_ctx_models = [mid for mid in candidate_pool if any(k in mid.lower() for k in ("31b", "90b", "120b", "550b", "glm-5", "deepseek"))]
                    if large_ctx_models:
                        non_large = [mid for mid in candidate_pool if mid not in large_ctx_models]
                        candidate_pool = large_ctx_models + non_large
                        logger.info(f"Large prompt detected ({est_tokens} tokens): isolated pool to large-context models.")

                if request.tools and not is_vision:
                    tool_incompatible = ["safety", "guard", "translate", "ising-calibration", "topic-control"]
                    tool_capable = [
                        mid for mid in candidate_pool
                        if not any(k in mid.lower() for k in tool_incompatible)
                    ]
                    if tool_capable:
                        candidate_pool = tool_capable

                def sort_candidates(mid: str):
                    throttled = 1 if self._rate_limited_until.get(mid, 0) > now else 0
                    rpm_over = 1 if self._get_recent_rpm(mid, now) >= MODEL_MAX_RPM else 0
                    busy = 1 if self._in_flight.get(mid, 0) >= MODEL_MAX_CONCURRENCY else 0
                    in_flight_count = self._in_flight.get(mid, 0)

                    lat = self._latencies.get(mid, 1.0)
                    rel = self._reliability.get(mid, 1.0)
                    tps = self._tps.get(mid, 40.0)
                    perf_score = (1.0 / max(0.01, lat)) * (rel ** 2) * (1.0 + 0.01 * tps)

                    return (throttled, rpm_over, busy, in_flight_count, -perf_score)

                if not category_target and not is_vision:
                    candidate_pool.sort(key=sort_candidates)
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
                else:
                    candidate_ids = candidate_pool

        tried_models = set()
        last_error = None
        attempts = len(candidate_ids)

        for selected_id in candidate_ids:
            if selected_id in tried_models:
                continue
            tried_models.add(selected_id)

            provider = self._get_provider_name(selected_id)
            current_latency = self._latencies.get(selected_id, 0.0)
            current_rpm = self._get_recent_rpm(selected_id, time.time())
            in_flight_num = self._in_flight.get(selected_id, 0)
            logger.info(f"Routing request (attempt {len(tried_models)}/{attempts}) -> {provider} :: {selected_id} (latency: {current_latency:.3f}s, rpm: {current_rpm}/{MODEL_MAX_RPM}, in-flight: {in_flight_num}, stream={request.stream})")

            t0 = time.time()
            self._record_request_dispatch(selected_id, t0)
            self._in_flight[selected_id] = in_flight_num + 1
            try:
                base_url, _, keys_to_try = self._get_provider_info(selected_id)
                for k_idx, current_key in enumerate(keys_to_try):
                    try:
                        request.model = selected_id
                        response = await call_provider_endpoint(current_key, selected_id, request, base_url)
                        elapsed = time.time() - t0
                        self._record_success(selected_id, elapsed)
                        logger.success(f"Request completed successfully via {provider} :: {selected_id} ({elapsed:.3f}s)")
                        return response
                    except HTTPException as e:
                        if e.status_code in (429, 400, 404, 500, 502, 503) and k_idx < len(keys_to_try) - 1:
                            logger.warning(f"Model {provider} :: {selected_id} error {e.status_code} on key {current_key[:8]}..., retrying next API key...")
                            await asyncio.sleep(0.1)
                            continue
                        raise
            except HTTPException as e:
                last_error = e
                self._record_failure(selected_id, status_code=e.status_code)
                if e.status_code in (429, 402):
                    logger.warning(f"Model {provider} :: {selected_id} returned status {e.status_code} (Rate Limited/Billing), backing off and failing over...")
                elif e.status_code == 404:
                    logger.warning(f"Model {provider} :: {selected_id} returned 404 (Not Found), removing from pool and failing over...")
                elif e.status_code in (400, 500, 502, 503):
                    logger.warning(f"Model {provider} :: {selected_id} returned status {e.status_code} (Unsupported/Server Error), failing over to next candidate...")
                else:
                    logger.warning(f"Model {provider} :: {selected_id} returned status {e.status_code}, failing over...")
            except Exception as e:
                last_error = e
                self._record_failure(selected_id, status_code=500)
                logger.error(f"Error calling {provider} :: {selected_id}: {e}, failing over...")
            finally:
                self._in_flight[selected_id] = max(0, self._in_flight.get(selected_id, 1) - 1)

        if last_error:
            raise last_error
        raise HTTPException(status_code=503, detail="No healthy model endpoints available in pool.")
