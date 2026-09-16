import asyncio
import json
import os
import time
from fastapi import HTTPException, Request, Response
import httpx

from nim_router.config import (
    get_rate_limit_cooldown,
    get_primary_pool_size,
    get_model_max_rpm,
    get_model_max_concurrency,
    get_max_latency_threshold,
    get_health_refresh_interval,
    get_quality_floor,
    NIM_API_BASE,
    OPENROUTER_API_BASE,
    OPENCODE_API_BASE,
    GROQ_API_BASE,
    CEREBRAS_API_BASE,
    BAI_API_BASE,
    get_primary_model,
    get_routing_strategy,
)
from nim_router.combos import get_combo, load_combos
from nim_router.logger import logger
from nim_router.schemas import ChatCompletionRequest
from nim_router.catalog import is_banned_model, load_fallback_models
from nim_router.classifier import (
    is_tool_model,
    is_vision_model,
    is_coding_model,
    is_reasoning_model,
    is_moe_model,
    is_chat_model,
    is_vision_request,
    estimate_token_count,
)
from nim_router.client import probe_model, discover_models, call_provider_endpoint
from nim_router.catalog import is_banned_model, load_fallback_models, get_provider_name as _catalog_get_provider_name, save_working_models
from nim_router.tracker import get_usage_tracker

class ModelRouter:
    def __init__(self, api_key: str | list[str], openrouter_key: str = "", opencode_key: str = "", groq_keys: str | list[str] = "", cerebras_keys: str | list[str] = "", bai_key: str = "", strategy: str = ""):
        self.tracker = get_usage_tracker()
        if isinstance(api_key, list):
            self.api_keys = [k.strip() for k in api_key if k.strip()]
        else:
            self.api_keys = [k.strip() for k in (api_key or "").split(",") if k.strip()]
        if not self.api_keys:
            self.api_keys = [""]
        self.api_key = self.api_keys[0]

        self.strategy = (strategy or get_routing_strategy()).strip().lower()
        self.openrouter_key = openrouter_key.strip()
        self.opencode_key = opencode_key.strip()
        self.bai_key = bai_key.strip()

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
        self._quality: dict[str, float] = {}
        self._quality_n: dict[str, int] = {}
        self._rate_limited_until: dict[str, float] = {}
        self._key_cooldowns: dict[tuple[str, str], float] = {}
        self._consecutive_failures: dict[str, int] = {}
        self._request_history: dict[str, list[float]] = {}
        self._in_flight: dict[str, int] = {}
        self._healthy_pool: list[str] = []
        self._pool_updated: float = 0
        self._model_providers: dict[str, str] = {}
        self._write_lock = asyncio.Lock()
        self._is_probing: bool = False
        self._last_probe_time: float = time.time()
        self._probe_count: int = 0
        self._bg_probe_task: asyncio.Task | None = None

    def _get_next_api_key(self) -> str:
        key = self.api_keys[self.key_index % len(self.api_keys)]
        self.key_index = (self.key_index + 1) % len(self.api_keys)
        return key

    def _get_provider_name(self, model_id: str, overrides: dict[str, str] | None = None) -> str:
        mid_clean = model_id
        for prefix in ("[NVIDIA] ", "[OpenRouter] ", "[OpenCode] ", "[Groq] ", "[Cerebras] ", "[BAI] ", "[Category] "):
            if mid_clean.startswith(prefix):
                mid_clean = mid_clean[len(prefix):].strip()
        if overrides and mid_clean in overrides:
            return overrides[mid_clean]
        if mid_clean in self._model_providers:
            return self._model_providers[mid_clean]
        return _catalog_get_provider_name(mid_clean)

    def _get_provider_info(self, model_id: str, overrides: dict[str, str] | None = None) -> tuple[str, str, list[str]]:
        provider = self._get_provider_name(model_id, overrides)
        now = time.time()

        if provider == "OpenRouter":
            keys = [self.openrouter_key] if self.openrouter_key else [""]
            base_url = OPENROUTER_API_BASE
        elif provider == "OpenCode":
            keys = [self.opencode_key] if self.opencode_key else [""]
            base_url = OPENCODE_API_BASE
        elif provider == "BAI":
            keys = [self.bai_key] if self.bai_key else [""]
            base_url = BAI_API_BASE
        elif provider == "Groq":
            keys = self.groq_keys if self.groq_keys else [""]
            base_url = GROQ_API_BASE
            rotated = keys[self.groq_key_index:] + keys[:self.groq_key_index]
            self.groq_key_index = (self.groq_key_index + 1) % len(keys)
            keys = rotated
        elif provider == "Cerebras":
            keys = self.cerebras_keys if self.cerebras_keys else [""]
            base_url = CEREBRAS_API_BASE
            rotated = keys[self.cerebras_key_index:] + keys[:self.cerebras_key_index]
            self.cerebras_key_index = (self.cerebras_key_index + 1) % len(keys)
            keys = rotated
        else:
            keys = self.api_keys if self.api_keys else [""]
            base_url = NIM_API_BASE
            rotated = keys[self.key_index:] + keys[:self.key_index]
            self.key_index = (self.key_index + 1) % len(keys)
            keys = rotated

        healthy_keys = [k for k in keys if self._key_cooldowns.get((provider, k), 0.0) <= now]
        cooling_keys = [k for k in keys if self._key_cooldowns.get((provider, k), 0.0) > now]

        sorted_keys = healthy_keys + cooling_keys if healthy_keys else keys
        primary_key = sorted_keys[0] if sorted_keys else ""
        return base_url, primary_key, sorted_keys

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
            self.cerebras_keys,
            self.bai_key
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
        if now - record.get("last_check", 0) > get_health_refresh_interval():
            record["failures"] = 0
            record["last_check"] = now
            record["healthy"] = True
        return record.get("healthy", True)

    def _record_key_failure(self, provider: str, key: str, model_id: str, status_code: int, retry_after: float | None = None):
        now = time.time()
        key_short = key[:8] if key else "default"
        key_ident = f"{provider}:{key_short}"
        fail_count = self._consecutive_failures.get(key_ident, 0) + 1
        self._consecutive_failures[key_ident] = fail_count

        if status_code in (429, 402, 503):
            if retry_after is not None and retry_after > 0:
                cooldown_sec = retry_after
            else:
                cooldown_sec = min(60.0, max(5.0, 5.0 * (2 ** (fail_count - 1))))

            cooldown_until = now + cooldown_sec
            if key:
                self._key_cooldowns[(provider, key)] = cooldown_until
            self._rate_limited_until[model_id] = cooldown_until
            logger.warning(
                f"Key {key_ident} for model '{model_id}' cooling down for {cooldown_sec:.1f}s "
                f"(status={status_code}, retry_after_hdr={retry_after}, consecutive_fails={fail_count})"
            )

    def _record_key_success(self, provider: str, key: str, model_id: str):
        key_short = key[:8] if key else "default"
        key_ident = f"{provider}:{key_short}"
        self._consecutive_failures.pop(key_ident, None)
        if key:
            self._key_cooldowns.pop((provider, key), None)
        self._consecutive_failures.pop(model_id, None)

    def _record_failure(self, model_id: str, status_code: int = 500):
        now = time.time()
        if status_code in (413, 422):
            logger.debug(
                f"Model {model_id} rejected request payload (HTTP {status_code}); not penalizing model health."
            )
            return
        cur_rel = self._reliability.get(model_id, 1.0)
        self._reliability[model_id] = max(0.05, 0.7 * cur_rel)

        if status_code in (429, 402):
            if model_id not in self._rate_limited_until or self._rate_limited_until[model_id] <= now:
                self._rate_limited_until[model_id] = now + get_rate_limit_cooldown()
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
        """Record a successful request. token_count should be generated completion tokens for calculating TPS."""
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

    def _resolve_combo_models(self, declared: list[str], pool: list[str]) -> tuple[list[str], dict[str, str]]:
        def norm(s: str) -> str:
            return s.lower().replace("-", "").replace("/", "").replace(".", "")

        catalog: list[tuple[str, str]] = []
        for m in self.models:
            mid = m.get("id")
            if mid:
                catalog.append((mid, (m.get("provider") or self._get_provider_name(mid) or "")))

        targets: list[str] = []
        overrides: dict[str, str] = {}
        seen: set[tuple[str, str]] = set()
        warned = getattr(type(self), "_combo_warn_cache", None)
        if warned is None:
            warned = type(self)._combo_warn_cache = set()

        def warn_once(key: str, msg: str):
            if key not in warned:
                warned.add(key)
                logger.warning(msg)

        for raw in declared:
            entry = (raw or "").strip()
            if not entry:
                continue

            want_provider = ""
            model_part = entry
            if "::" in entry:
                want_provider, model_part = entry.split("::", 1)
                want_provider = want_provider.strip().lower()
                model_part = model_part.strip()

            npart = norm(model_part)

            def prov_ok(prov: str) -> bool:
                return not want_provider or prov.lower() == want_provider

            exact = [
                (mid, prov) for mid, prov in catalog
                if mid.lower() == model_part.lower() and prov_ok(prov)
            ]
            loose = exact or [
                (mid, prov) for mid, prov in catalog
                if prov_ok(prov) and (norm(mid.split("/", 1)[-1]) == npart or norm(mid) == npart)
            ]

            if not loose:
                in_pool = model_part.lower() in {p.lower() for p in pool}
                warn_once(
                    ("nomatch", entry),
                    f"Combo entry '{entry}' does not match any discovered endpoint"
                    + (f" for provider '{want_provider}'" if want_provider else "")
                    + (" (id exists but not in the healthy pool)" if in_pool else "")
                    + "; skipping it instead of substituting a similarly named model."
                )
                continue

            mid, prov = loose[0]
            if len(loose) > 1 and not want_provider:
                warn_once(
                    ("ambiguous", entry),
                    f"Combo entry '{entry}' is ambiguous across providers "
                    f"({', '.join(p for _, p in loose)}); using '{prov}'. "
                    f"Pin it as '{prov}::{entry}' to make this deterministic."
                )
            if (mid, prov) in seen or mid in {m for m, _ in seen}:
                warn_once(
                    ("dupe", entry),
                    f"Combo entry '{entry}' resolves to '{prov}::{mid}', already used by an "
                    f"earlier slot; dropping the duplicate so the chain has no dead repeats."
                )
                continue
            seen.add((mid, prov))
            targets.append(mid)
            if prov:
                overrides[mid] = prov

        return targets, overrides

    def _record_quality_sample(self, model_id: str, degraded: bool):
        n = self._quality_n.get(model_id, 0)
        q = self._quality.get(model_id, 1.0) if n else 1.0
        obs = 0.0 if degraded else 1.0
        effective_n = min(n, 50)
        self._quality[model_id] = round((q * effective_n + obs) / (effective_n + 1), 4)
        self._quality_n[model_id] = n + 1

    def _quality_multiplier(self, model_id: str) -> float:
        if self._quality_n.get(model_id, 0) < 3:
            return 1.0
        floor = get_quality_floor()
        q = self._quality.get(model_id, 1.0)
        return floor + (1.0 - floor) * q

    def _build_healthy_pool(self) -> list[str]:
        now = time.time()
        max_rpm = get_model_max_rpm()
        max_concurrency = get_model_max_concurrency()
        all_ids = [m.get("id") for m in self.models if m.get("id") and not self._is_banned_model(m.get("id"))]
        healthy = [mid for mid in all_ids if self._is_model_healthy(mid)]

        if not healthy and all_ids:
            logger.warning("All models in pool were marked unhealthy; auto-resetting health states to restore availability.")
            self._health.clear()
            self._rate_limited_until.clear()
            healthy = list(all_ids)

        def sort_key(mid: str):
            throttled = 1 if self._rate_limited_until.get(mid, 0) > now else 0
            rpm_over = 1 if self._get_recent_rpm(mid, now) >= max_rpm else 0
            busy = 1 if self._in_flight.get(mid, 0) >= max_concurrency else 0
            in_flight_count = self._in_flight.get(mid, 0)

            lat = self._latencies.get(mid, 1.0)
            rel = self._reliability.get(mid, 1.0)
            tps = self._tps.get(mid, 40.0)
            perf_score = (1.0 / max(0.01, lat)) * (rel ** 2) * (1.0 + 0.01 * tps) * self._quality_multiplier(mid)

            return (throttled, rpm_over, busy, in_flight_count, -perf_score)

        healthy.sort(key=sort_key)
        return healthy

    def _load_runtime_state(self):
        try:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            state_path = os.path.join(base_dir, "config", "runtime_state.json")
            if os.path.exists(state_path):
                age = time.time() - os.path.getmtime(state_path)
                if age <= 3600:
                    with open(state_path, "r") as f:
                        state = json.load(f)
                    self._latencies.update(state.get("latencies", {}))
                    self._reliability.update(state.get("reliability", {}))
                    self._quality.update(state.get("quality", {}))
                    self._quality_n.update(state.get("quality_n", {}))
                    loaded_tps = state.get("tps", {})
                    # Sanitize any legacy corrupted TPS values that previously included prompt tokens
                    for mid, tps_val in loaded_tps.items():
                        if tps_val > 400.0:
                            loaded_tps[mid] = 40.0
                    self._tps.update(loaded_tps)

            # Calibrate model TPS from actual completed tokens recorded in usage.db if available
            if hasattr(self, "tracker") and self.tracker:
                with self.tracker._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT model, completion_tokens, latency_ms
                        FROM request_logs
                        WHERE status_code >= 200 AND status_code < 400 AND completion_tokens > 0 AND latency_ms > 50
                        ORDER BY id ASC
                    """)
                    for row in cursor.fetchall():
                        m = row["model"]
                        c_tok = row["completion_tokens"]
                        lat_s = row["latency_ms"] / 1000.0
                        meas = c_tok / lat_s
                        cur = self._tps.get(m, 40.0)
                        self._tps[m] = round(0.7 * cur + 0.3 * meas, 2)
        except Exception:
            pass

    def _save_runtime_state(self):
        try:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            config_dir = os.path.join(base_dir, "config")
            os.makedirs(config_dir, exist_ok=True)
            state_path = os.path.join(config_dir, "runtime_state.json")
            with open(state_path, "w") as f:
                json.dump({
                    "latencies": self._latencies,
                    "reliability": self._reliability,
                    "tps": self._tps,
                    "quality": self._quality,
                    "quality_n": self._quality_n,
                }, f)
        except Exception:
            pass

    async def initialize(self):
        async with self._write_lock:
            self.models = self._load_fallback_models()
            self._load_runtime_state()
            for m in self.models:
                mid = m.get("id")
                if mid:
                    self._model_providers[mid] = m.get("provider") or self._get_provider_name(mid)
            self._healthy_pool = self._build_healthy_pool()
            self._pool_updated = time.time()

            nvidia_count = sum(1 for m in self.models if self._get_provider_name(m.get("id", "")) == "NVIDIA")
            or_count = sum(1 for m in self.models if self._get_provider_name(m.get("id", "")) == "OpenRouter")
            oc_count = sum(1 for m in self.models if self._get_provider_name(m.get("id", "")) == "OpenCode")
            groq_count = sum(1 for m in self.models if self._get_provider_name(m.get("id", "")) == "Groq")
            cerebras_count = sum(1 for m in self.models if self._get_provider_name(m.get("id", "")) == "Cerebras")
            bai_count = sum(1 for m in self.models if self._get_provider_name(m.get("id", "")) == "BAI")

            logger.success(
                f"nim-router initialized instantly with {len(self._healthy_pool)} working models in pool "
                f"(NVIDIA: {nvidia_count}, OpenRouter: {or_count}, OpenCode: {oc_count}, Groq: {groq_count}, Cerebras: {cerebras_count}, BAI: {bai_count})"
            )
            logger.info(f"Active routing strategy: {self.strategy}")
            self._last_probe_time = time.time()
        if self._bg_probe_task is None or self._bg_probe_task.done():
            self._bg_probe_task = asyncio.create_task(self._background_probe_loop())
        asyncio.create_task(self.refresh_models())

    async def _background_probe_loop(self):
        await asyncio.sleep(8)
        while True:
            try:
                interval = get_health_refresh_interval()
                await asyncio.sleep(interval)
                if not self._is_probing:
                    logger.info(f"Auto background health prober executing scheduled cycle (interval: {interval}s)...")
                    await self.refresh_models()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Background health prober error: {e}")
                await asyncio.sleep(10)

    async def refresh_models(self):
        if self._is_probing:
            logger.info("Probe already in progress; skipping duplicate run.")
            return
        self._is_probing = True
        try:
            self.strategy = get_routing_strategy()
            logger.info("Auto background health prober started: probing model catalog & endpoints...")
            new_models = await self._discover_models()
            if new_models:
                async with self._write_lock:
                    self.models = new_models
                    for m in self.models:
                        mid = m.get("id")
                        if mid:
                            self._model_providers[mid] = m.get("provider") or self._get_provider_name(mid)
                    self._healthy_pool = self._build_healthy_pool()
                    self._pool_updated = time.time()
                    logger.success(f"Refreshed pool: {len(self._healthy_pool)} active models available.")
                save_working_models(new_models)
                self._save_runtime_state()
            self._last_probe_time = time.time()
            self._probe_count += 1
            logger.success(f"Background health prober finished cycle #{self._probe_count}. Verified {len(self._healthy_pool)} working models.")
        except Exception as e:
            logger.error(f"Error during background model probing: {e}")
        finally:
            self._is_probing = False

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
        if not self.models:
            async with self._write_lock:
                if not self.models:
                    self.models = self._load_fallback_models()
                    for m in self.models:
                        mid = m.get("id")
                        if mid:
                            self._model_providers[mid] = m.get("provider") or self._get_provider_name(mid)
                    self._healthy_pool = self._build_healthy_pool()
                    self._pool_updated = time.time()

        if now - self._pool_updated > get_health_refresh_interval():
            self._pool_updated = now
            asyncio.create_task(self.refresh_models())

        requested_model = (request.model or "").strip()
        for prefix in ("[NVIDIA] ", "[OpenRouter] ", "[OpenCode] ", "[Groq] ", "[Cerebras] ", "[BAI] ", "[Category] "):
            if requested_model.startswith(prefix):
                requested_model = requested_model[len(prefix):].strip()

        req_lower = requested_model.lower()
        category_target = None
        if req_lower in ("nim-tools", "tools", "tool"):
            category_target = "tools"
        elif req_lower in ("nim-coding", "coding", "code"):
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
                    self._model_providers[mid] = m.get("provider") or self._get_provider_name(mid)
            candidate_pool = [m.get("id") for m in self.models if m.get("id")]

        is_vision = self._is_vision_request(request)
        has_tools = bool(request.tools or getattr(request, "functions", None))

        if is_vision:
            vision_capable = [mid for mid in candidate_pool if self._is_vision_model(mid)]
            if not vision_capable:
                all_ids = [m.get("id") for m in self.models if m.get("id")]
                vision_capable = [mid for mid in all_ids if self._is_vision_model(mid)]
            if vision_capable:
                other_candidates = [mid for mid in candidate_pool if mid not in vision_capable]
                candidate_pool = vision_capable + other_candidates
                logger.info(f"Vision payload detected: overriding target to {len(vision_capable)} vision-capable models first.")
            target_model = "nim-auto"
        elif has_tools and not category_target and (not requested_model or requested_model.lower() in ("nim-auto", "nim_auto", "auto")):
            tool_capable = [mid for mid in candidate_pool if is_tool_model(mid)]
            if not tool_capable:
                all_ids = [m.get("id") for m in self.models if m.get("id")]
                tool_capable = [mid for mid in all_ids if is_tool_model(mid)]
            if tool_capable:
                other_candidates = [mid for mid in candidate_pool if mid not in tool_capable]
                candidate_pool = tool_capable + other_candidates
                logger.info(f"Tool payload detected: prioritizing {len(tool_capable)} tool-capable models first.")
            target_model = "nim-auto"
        elif category_target:
            if category_target == "tools":
                cat_filtered = [mid for mid in candidate_pool if is_tool_model(mid)]
            elif category_target == "coding":
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
            target_model = "nim-auto"
        else:
            target_model = requested_model if (requested_model and requested_model.lower() not in ("nim-auto", "nim_auto", "auto")) else get_primary_model()

        combo = get_combo(requested_model) if requested_model else None
        combo_provider_overrides: dict[str, str] = {}
        if combo:
            combo_models = combo.get("models", [])
            strategy = combo.get("strategy", "fallback")

            resolved, combo_provider_overrides = self._resolve_combo_models(combo_models, candidate_pool)

            if strategy == "round_robin":
                if resolved:
                    start = self.model_index % len(resolved)
                    self.model_index = (self.model_index + 1) % len(resolved)
                    ordered = resolved[start:] + resolved[:start]
                else:
                    ordered = []
            else:
                ordered = resolved

            nim_auto_pool = [m for m in candidate_pool if m not in ordered]
            candidate_ids = ordered + nim_auto_pool
            logger.info(
                f"Combo '{combo['name']}' ({strategy}): routing through "
                f"{len(ordered)} models → nim-auto pool fallback"
            )

        elif target_model and target_model.lower() not in ("nim-auto", "nim_auto", "auto") and not is_vision:
            request.model = target_model
            if self._is_banned_model(target_model):
                logger.warning(f"Target model {target_model} is banned/non-chat; routing to healthy pool.")
                candidate_ids = candidate_pool
            else:
                if target_model in candidate_pool:
                    other_candidates = [mid for mid in candidate_pool if mid != target_model]
                    primary_ids = [target_model]
                else:
                    target_clean = target_model.lower().replace("-", "").replace("/", "").replace(".", "")
                    matching = [
                        mid for mid in candidate_pool
                        if target_clean in mid.lower().replace("-", "").replace("/", "").replace(".", "")
                        or mid.lower().replace("-", "").replace("/", "").replace(".", "") in target_clean
                    ]
                    if matching:
                        logger.info(f"Target model '{target_model}' matched candidate '{matching[0]}' in active pool.")
                        other_candidates = [mid for mid in candidate_pool if mid not in matching]
                        primary_ids = matching
                    else:
                        other_candidates = [mid for mid in candidate_pool if mid != target_model]
                        primary_ids = [target_model]

                candidate_ids = primary_ids + other_candidates
        else:
            if candidate_pool:
                fast_candidates = [mid for mid in candidate_pool if self._latencies.get(mid, 0.0) <= get_max_latency_threshold()]
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

            max_rpm = get_model_max_rpm()
            max_concurrency = get_model_max_concurrency()

            def sort_candidates(mid: str):
                throttled = 1 if self._rate_limited_until.get(mid, 0) > now else 0
                rpm_over = 1 if self._get_recent_rpm(mid, now) >= max_rpm else 0
                busy = 1 if self._in_flight.get(mid, 0) >= max_concurrency else 0
                in_flight_count = self._in_flight.get(mid, 0)

                is_vision_demotion = 1 if (not is_vision and self._is_vision_model(mid)) else 0

                lat = self._latencies.get(mid, 1.0)
                rel = self._reliability.get(mid, 1.0)
                tps = self._tps.get(mid, 40.0)
                perf_score = (1.0 / max(0.01, lat)) * (rel ** 2) * (1.0 + 0.01 * tps) * self._quality_multiplier(mid)

                return (throttled, rpm_over, busy, is_vision_demotion, in_flight_count, -perf_score)

            if not category_target and not is_vision:
                candidate_pool.sort(key=sort_candidates)
                if self.strategy == "fallback":
                    candidate_ids = candidate_pool
                else:
                    top_size = min(get_primary_pool_size(), len(candidate_pool))
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
        context_rejected_providers = set()

        for selected_id in candidate_ids:
            if selected_id in tried_models:
                continue
            tried_models.add(selected_id)

            provider = self._get_provider_name(selected_id, combo_provider_overrides)
            if provider in context_rejected_providers:
                logger.info(f"Skipping {provider} :: {selected_id}: provider already rejected this payload size (413).")
                continue
            current_latency = self._latencies.get(selected_id, 0.0)
            current_rpm = self._get_recent_rpm(selected_id, time.time())
            in_flight_num = self._in_flight.get(selected_id, 0)
            logger.info(f"Routing request (attempt {len(tried_models)}/{attempts}) -> {provider} :: {selected_id} (latency: {current_latency:.3f}s, rpm: {current_rpm}/{get_model_max_rpm()}, in-flight: {in_flight_num}, stream={request.stream})")

            t0 = time.time()
            self._record_request_dispatch(selected_id, t0)
            self._in_flight[selected_id] = in_flight_num + 1
            try:
                base_url, _, keys_to_try = self._get_provider_info(selected_id, combo_provider_overrides)
                for k_idx, current_key in enumerate(keys_to_try):
                    now_check = time.time()
                    cool_until = self._key_cooldowns.get((provider, current_key), 0.0)
                    if cool_until > now_check and len(keys_to_try) > 1:
                        logger.debug(f"Skipping key {current_key[:8]}... for {provider} (cooling down for {cool_until - now_check:.1f}s)")
                        continue
                    try:
                        request.model = selected_id
                        recorded_tokens = [0]
                        usage_recorded = False

                        def on_request_usage(p_tok: int, c_tok: int, tot_tok: int, is_est: bool, degraded: bool = False):
                            nonlocal usage_recorded
                            if usage_recorded:
                                return
                            usage_recorded = True
                            recorded_tokens[0] = c_tok
                            now_done = time.time()
                            lat_ms = (now_done - t0) * 1000.0
                            self.tracker.record_request(
                                provider=provider,
                                model=selected_id,
                                api_key_masked=current_key[-6:] if len(current_key) >= 6 else current_key,
                                status_code=200,
                                latency_ms=lat_ms,
                                stream=bool(request.stream),
                                prompt_tokens=p_tok,
                                completion_tokens=c_tok,
                                total_tokens=tot_tok,
                                is_estimated=is_est,
                                timestamp=t0
                            )
                            self._record_quality_sample(selected_id, degraded)
                            self._record_success(selected_id, now_done - t0, token_count=c_tok)

                        response = await call_provider_endpoint(
                            current_key,
                            selected_id,
                            request,
                            base_url,
                            on_usage=on_request_usage
                        )
                        elapsed = time.time() - t0
                        if not usage_recorded and not request.stream:
                            self._record_success(selected_id, elapsed, token_count=recorded_tokens[0])
                        self._record_key_success(provider, current_key, selected_id)
                        logger.success(f"Request completed successfully via {provider} :: {selected_id} ({elapsed:.3f}s)")
                        return response
                    except HTTPException as e:
                        retry_after_hdr = e.headers.get("Retry-After") if e.headers else None
                        retry_sec = float(retry_after_hdr) if retry_after_hdr else None
                        self._record_key_failure(provider, current_key, selected_id, e.status_code, retry_after=retry_sec)
                        self.tracker.record_request(
                            provider=provider,
                            model=selected_id,
                            api_key_masked=current_key[-6:] if len(current_key) >= 6 else current_key,
                            status_code=e.status_code,
                            latency_ms=(time.time() - t0) * 1000.0,
                            stream=bool(request.stream),
                            prompt_tokens=0,
                            completion_tokens=0,
                            total_tokens=0,
                            is_estimated=False,
                            timestamp=t0
                        )
                        if e.status_code in (429, 400, 404, 500, 502, 503) and k_idx < len(keys_to_try) - 1:
                            logger.warning(f"Model {provider} :: {selected_id} error {e.status_code} on key {current_key[:8]}..., retrying next API key...")
                            await asyncio.sleep(0.1)
                            continue
                        raise
            except HTTPException as e:
                last_error = e
                self._record_failure(selected_id, status_code=e.status_code)
                if e.status_code == 413:
                    context_rejected_providers.add(provider)
                    logger.warning(f"Model {provider} :: {selected_id} returned 413 (payload too large), skipping remaining {provider} candidates...")
                elif e.status_code in (429, 402):
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
                self.tracker.record_request(
                    provider=provider,
                    model=selected_id,
                    api_key_masked=current_key[-6:] if len(current_key) >= 6 else current_key,
                    status_code=500,
                    latency_ms=(time.time() - t0) * 1000.0,
                    stream=bool(request.stream),
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    is_estimated=False,
                    timestamp=t0
                )
                logger.error(f"Error calling {provider} :: {selected_id}: {e}, failing over...")
            finally:
                self._in_flight[selected_id] = max(0, self._in_flight.get(selected_id, 1) - 1)

        if last_error:
            raise last_error
        raise HTTPException(status_code=503, detail="No healthy model endpoints available in pool.")
