import asyncio
import json
import os
import time
import secrets
from contextlib import asynccontextmanager
from typing import Optional

from nim_router.classifier import (
    is_vision_model,
    is_moe_model,
    is_tool_model,
    get_model_capabilities,
    get_model_tasks,
)

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from nim_router.config import (
    get_nvidia_keys,
    get_openrouter_key,
    get_opencode_key,
    get_groq_keys,
    get_cerebras_keys,
    get_bai_key,
    get_routing_strategy,
    get_primary_model,
    get_health_refresh_interval,
    reload_env,
    update_setting,
    _load_settings,
    _ENV_FILE,
    verify_dashboard_password,
    set_dashboard_password,
    is_password_configured,
)
from nim_router.combos import (
    load_combos,
    create_combo,
    update_combo,
    delete_combo,
    get_combo,
)
from nim_router.engine import ModelRouter
from nim_router.logger import (
    logger,
    register_log_subscriber,
    unregister_log_subscriber,
    get_recent_logs,
)
from nim_router.client import get_shared_client, close_shared_client
from nim_router.catalog import save_working_models

_router_instance: Optional[ModelRouter] = None
_server_start_time: float = time.time()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _router_instance, _server_start_time
    _server_start_time = time.time()
    nvidia_keys = get_nvidia_keys()
    openrouter_key = get_openrouter_key()
    opencode_key = get_opencode_key()
    groq_keys = get_groq_keys()
    cerebras_keys = get_cerebras_keys()
    bai_key = get_bai_key()
    strategy = get_routing_strategy()

    if not nvidia_keys and not openrouter_key and not opencode_key and not groq_keys and not cerebras_keys and not bai_key:
        logger.warning("No API keys found in environment (.env). Please configure NVIDIA_API_KEYS, OPENROUTER_API_KEY, GROQ_API_KEY, CEREBRAS_API_KEY, or BAI_API_KEY.")

    _router_instance = ModelRouter(
        api_key=nvidia_keys,
        openrouter_key=openrouter_key,
        opencode_key=opencode_key,
        groq_keys=groq_keys,
        cerebras_keys=cerebras_keys,
        bai_key=bai_key,
        strategy=strategy
    )
    get_shared_client()
    await _router_instance.initialize()
    yield
    await close_shared_client()
    logger.info("nim-router shutting down")

def create_app() -> FastAPI:
    app = FastAPI(title="NIM Router", lifespan=lifespan)

    def _enrich_combos(combos: list[dict], model_items: list[dict], max_latency_threshold: float = 3.0) -> list[dict]:
        models_by_id = {m["id"]: m for m in model_items}
        models_by_clean = {
            m["id"].lower().replace("-", "").replace("/", "").replace(".", ""): m
            for m in model_items
        }

        enriched = []
        for c in combos:
            c_copy = dict(c)
            unavailable = []
            high_latency = []
            for mid in c.get("models", []):
                m = models_by_id.get(mid)
                if not m:
                    clean = mid.lower().replace("-", "").replace("/", "").replace(".", "")
                    m = models_by_clean.get(clean)
                    if not m:
                        for k, v in models_by_clean.items():
                            if clean in k or k in clean:
                                m = v
                                break
                if not m or not m.get("healthy", True):
                    unavailable.append(mid)
                elif m.get("latency", 0) > max_latency_threshold:
                    high_latency.append({
                        "id": mid,
                        "latency": m.get("latency", 0)
                    })
            c_copy["unavailable_models"] = unavailable
            c_copy["high_latency_models"] = high_latency
            c_copy["has_unavailable"] = len(unavailable) > 0
            c_copy["has_high_latency"] = len(high_latency) > 0
            enriched.append(c_copy)
        return enriched

    _SESSIONS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", ".sessions.json")
    SESSION_TTL_SECONDS = 86400 * 30  # 30 days

    def _load_sessions() -> dict[str, float]:
        if os.path.exists(_SESSIONS_FILE):
            try:
                with open(_SESSIONS_FILE, "r") as f:
                    data = json.load(f)
                    now = time.time()
                    return {k: float(v) for k, v in data.items() if now - float(v) < SESSION_TTL_SECONDS}
            except Exception:
                pass
        return {}

    def _save_sessions(sessions: dict[str, float]):
        try:
            os.makedirs(os.path.dirname(_SESSIONS_FILE), exist_ok=True)
            with open(_SESSIONS_FILE, "w") as f:
                json.dump(sessions, f)
        except Exception:
            pass

    _active_sessions = _load_sessions()

    def _extract_token(request: Request) -> Optional[str]:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            t = auth_header[7:].strip()
            if t:
                return t
        x_tok = request.headers.get("X-Dashboard-Token", "").strip()
        if x_tok:
            return x_tok
        c_tok = request.cookies.get("nim_session", "").strip()
        if c_tok:
            return c_tok
        q_tok = request.query_params.get("token", "").strip()
        if q_tok:
            return q_tok
        return None

    def _is_authenticated(request: Request) -> bool:
        token = _extract_token(request)
        if not token:
            return False
        session_time = _active_sessions.get(token)
        if not session_time:
            return False
        if time.time() - session_time > SESSION_TTL_SECONDS:
            _active_sessions.pop(token, None)
            _save_sessions(_active_sessions)
            return False
        return True

    def _check_auth(request: Request):
        if not _is_authenticated(request):
            raise HTTPException(status_code=401, detail="Authentication required")

    @app.get("/api/auth/status")
    async def get_auth_status(request: Request):
        return {
            "authenticated": _is_authenticated(request),
            "password_configured": is_password_configured(),
        }

    @app.post("/api/auth/login")
    async def login_endpoint(request: Request, response: Response):
        try:
            body = await request.json()
        except Exception:
            body = {}
        password = str(body.get("password", "")).strip()
        if not verify_dashboard_password(password):
            raise HTTPException(status_code=401, detail="Invalid password")

        token = secrets.token_urlsafe(32)
        _active_sessions[token] = time.time()
        _save_sessions(_active_sessions)

        response.set_cookie(
            key="nim_session",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=SESSION_TTL_SECONDS,
            path="/"
        )
        return {
            "success": True,
            "token": token,
            "message": "Authenticated successfully"
        }

    @app.post("/api/auth/logout")
    async def logout_endpoint(request: Request, response: Response):
        token = _extract_token(request)
        if token and token in _active_sessions:
            _active_sessions.pop(token, None)
            _save_sessions(_active_sessions)
        response.delete_cookie(key="nim_session", path="/")
        return {"success": True, "message": "Logged out successfully"}

    @app.post("/api/auth/change-password")
    async def change_password_endpoint(request: Request):
        _check_auth(request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        current_pw = str(body.get("current_password", "")).strip()
        new_pw = str(body.get("new_password", "")).strip()

        if not verify_dashboard_password(current_pw):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

        if not new_pw or len(new_pw) < 4:
            raise HTTPException(status_code=400, detail="New password must be at least 4 characters long")

        set_dashboard_password(new_pw)
        logger.success("Dashboard access password updated successfully.")
        return {"success": True, "message": "Password updated successfully"}

    @app.get("/api/dashboard/stats")
    async def get_dashboard_stats(request: Request):
        _check_auth(request)
        if not _router_instance:
            return {"status": "initializing"}

        now = time.time()
        primary_model = get_primary_model()
        strategy = get_routing_strategy()
        settings = _load_settings()

        nv_keys = get_nvidia_keys()
        groq_keys = get_groq_keys()
        cerebras_keys = get_cerebras_keys()
        or_key = get_openrouter_key()
        oc_key = get_opencode_key()
        bai_key = get_bai_key()

        total_models = len(_router_instance.models)
        healthy_pool = _router_instance._healthy_pool
        in_flight_total = sum(_router_instance._in_flight.values())

        tracker = getattr(_router_instance, "tracker", None)
        analytics = tracker.get_analytics(time_range="all") if tracker else {}
        usage_summary = analytics.get("summary") or {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "success_rate": 100.0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "avg_latency_ms": 0.0
        }
        usage_providers = analytics.get("providers", [])

        if usage_summary.get("total_requests", 0) > 0 and usage_summary.get("avg_latency_ms"):
            avg_latency = round(usage_summary["avg_latency_ms"] / 1000.0, 3)
        else:
            latencies = [
                _router_instance._latencies.get(m.get("id"), 1.0)
                for m in _router_instance.models if m.get("id") and _router_instance._latencies.get(m.get("id"))
            ]
            avg_latency = round(sum(latencies) / len(latencies), 3) if latencies else None

        tps_vals = [
            _router_instance._tps[m.get("id")]
            for m in _router_instance.models
            if m.get("id") and m.get("id") in _router_instance._tps
        ]
        avg_tps = round(sum(tps_vals) / len(tps_vals), 1) if tps_vals else None

        all_ids = [m.get("id") for m in _router_instance.models if m.get("id")]
        vision_pool_size = sum(1 for mid in all_ids if is_vision_model(mid))
        moe_pool_size = sum(1 for mid in all_ids if is_moe_model(mid))

        model_items = []
        for m in _router_instance.models:
            mid = m.get("id")
            if not mid:
                continue
            prov = _router_instance._get_provider_name(mid)
            is_healthy = _router_instance._is_model_healthy(mid)
            lat = round(_router_instance._latencies.get(mid, 0.45), 3)
            tps = round(_router_instance._tps.get(mid, 45.0), 1)
            rel = round(_router_instance._reliability.get(mid, 1.0), 2)
            cooling = _router_instance._rate_limited_until.get(mid, 0) > now
            model_items.append({
                "id": mid,
                "provider": prov,
                "latency": lat,
                "tps": tps,
                "reliability": rel,
                "healthy": is_healthy and not cooling,
                "is_primary": (mid == primary_model),
                "in_flight": _router_instance._in_flight.get(mid, 0),
                "capabilities": get_model_capabilities(mid, prov, m),
                "tasks": get_model_tasks(mid, prov, m),
            })

        max_lat_threshold = settings.get("max_latency_threshold", 3.0)
        enriched_combos = _enrich_combos(load_combos(), model_items, max_lat_threshold)

        prov_models_count = {}
        for m in _router_instance.models:
            p = _router_instance._get_provider_name(m.get("id", ""))
            prov_models_count[p] = prov_models_count.get(p, 0) + 1

        interval_sec = get_health_refresh_interval()
        last_probe = getattr(_router_instance, "_last_probe_time", now)
        elapsed_sec = max(0, int(now - last_probe))
        next_probe_sec = max(0, interval_sec - (elapsed_sec % interval_sec)) if interval_sec > 0 else 0

        probing_status = {
            "is_probing": getattr(_router_instance, "_is_probing", False),
            "last_probe_time": last_probe,
            "elapsed_seconds": elapsed_sec,
            "interval_seconds": interval_sec,
            "next_probe_seconds": next_probe_sec,
            "probe_count": getattr(_router_instance, "_probe_count", 1),
        }

        return {
            "status": "online",
            "uptime_seconds": int(now - _server_start_time),
            "primary_model": primary_model,
            "routing_strategy": strategy,
            "max_latency_threshold": max_lat_threshold,
            "combos": enriched_combos,
            "total_models": total_models,
            "healthy_pool_size": len(healthy_pool),
            "in_flight_total": in_flight_total,
            "avg_latency": avg_latency,
            "avg_tps": avg_tps,
            "vision_pool_size": vision_pool_size,
            "moe_pool_size": moe_pool_size,
            "models": model_items,
            "probing_status": probing_status,
            "providers": {
                "NVIDIA": {"keys_count": len(nv_keys), "active": len(nv_keys) > 0, "models_count": prov_models_count.get("NVIDIA", 0)},
                "Groq": {"keys_count": len(groq_keys), "active": len(groq_keys) > 0, "models_count": prov_models_count.get("Groq", 0)},
                "Cerebras": {"keys_count": len(cerebras_keys), "active": len(cerebras_keys) > 0, "models_count": prov_models_count.get("Cerebras", 0)},
                "OpenRouter": {"keys_count": 1 if or_key else 0, "active": bool(or_key), "models_count": prov_models_count.get("OpenRouter", 0)},
                "OpenCode": {"keys_count": 1 if oc_key else 0, "active": bool(oc_key), "models_count": prov_models_count.get("OpenCode", 0)},
                "BAI": {"keys_count": 1 if bai_key else 0, "active": bool(bai_key), "models_count": prov_models_count.get("BAI", 0)},
            },
            "usage_summary": usage_summary,
            "usage_providers": usage_providers
        }

    @app.get("/api/dashboard/usage")
    async def get_dashboard_usage(request: Request, time_range: str = "all"):
        _check_auth(request)
        tracker = getattr(_router_instance, "tracker", None)
        if not tracker:
            return {
                "time_range": time_range,
                "summary": {
                    "total_requests": 0,
                    "successful_requests": 0,
                    "failed_requests": 0,
                    "success_rate": 100.0,
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_tokens": 0,
                    "avg_latency_ms": 0.0
                },
                "providers": [],
                "models": [],
                "recent_activity": []
            }
        return tracker.get_analytics(time_range=time_range)

    @app.post("/api/dashboard/usage/reset")
    async def reset_dashboard_usage(request: Request):
        _check_auth(request)
        tracker = getattr(_router_instance, "tracker", None)
        if tracker:
            tracker.reset_analytics()
        return {"success": True, "message": "Usage analytics reset"}

    @app.get("/api/keys")
    async def get_keys_info(request: Request):
        _check_auth(request)
        def mask(k: str) -> str:
            if not k:
                return ""
            return f"{k[:6]}...{k[-4:]}" if len(k) > 10 else f"{k[:4]}..."

        nv_keys = get_nvidia_keys()
        groq_keys = get_groq_keys()
        cerebras_keys = get_cerebras_keys()
        or_key = get_openrouter_key()
        oc_key = get_opencode_key()
        bai_key = get_bai_key()

        return {
            "providers": [
                {"id": "NVIDIA", "name": "NVIDIA NIM", "env_var": "NVIDIA_API_KEYS", "keys": [mask(k) for k in nv_keys], "count": len(nv_keys)},
                {"id": "Groq", "name": "Groq LPU", "env_var": "GROQ_API_KEYS", "keys": [mask(k) for k in groq_keys], "count": len(groq_keys)},
                {"id": "Cerebras", "name": "Cerebras Wafer-Scale", "env_var": "CEREBRAS_API_KEYS", "keys": [mask(k) for k in cerebras_keys], "count": len(cerebras_keys)},
                {"id": "OpenRouter", "name": "OpenRouter Free", "env_var": "OPENROUTER_API_KEY", "keys": [mask(or_key)] if or_key else [], "count": 1 if or_key else 0},
                {"id": "OpenCode", "name": "OpenCode Zen", "env_var": "OPENCODE_API_KEY", "keys": [mask(oc_key)] if oc_key else [], "count": 1 if oc_key else 0},
                {"id": "BAI", "name": "B.AI Free", "env_var": "BAI_API_KEY", "keys": [mask(bai_key)] if bai_key else [], "count": 1 if bai_key else 0},
            ]
        }

    @app.post("/api/keys")
    async def update_provider_keys(request: Request):
        _check_auth(request)
        body = await request.json()
        provider = body.get("provider", "").strip().upper()
        action = body.get("action", "set")
        key_val = body.get("key", "").strip()

        env_map = {
            "NVIDIA": "NVIDIA_API_KEYS",
            "GROQ": "GROQ_API_KEYS",
            "CEREBRAS": "CEREBRAS_API_KEYS",
            "OPENROUTER": "OPENROUTER_API_KEY",
            "OPENCODE": "OPENCODE_API_KEY",
            "BAI": "BAI_API_KEY",
        }
        env_var = env_map.get(provider)
        if not env_var:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

        env_vars = {}
        if os.path.exists(_ENV_FILE):
            with open(_ENV_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line and not line.startswith("#"):
                        parts = line.split("=", 1)
                        env_vars[parts[0].strip()] = parts[1].strip()

        current_val = env_vars.get(env_var, "")
        current_list = [k.strip() for k in current_val.split(",") if k.strip()]

        if action == "clear":
            env_vars.pop(env_var, None)
            env_vars.pop(env_var.rstrip("S"), None)
        elif action == "add":
            if key_val:
                new_keys = [k.strip() for k in key_val.split(",") if k.strip()]
                for nk in new_keys:
                    if nk not in current_list:
                        current_list.append(nk)
                env_vars[env_var] = ",".join(current_list)
        elif action in ("delete", "remove"):
            idx = body.get("index")
            if idx is not None and isinstance(idx, int) and 0 <= idx < len(current_list):
                current_list.pop(idx)
            elif key_val and key_val in current_list:
                current_list.remove(key_val)
            if current_list:
                env_vars[env_var] = ",".join(current_list)
            else:
                env_vars.pop(env_var, None)
                env_vars.pop(env_var.rstrip("S"), None)
        elif action in ("update", "replace") or (action == "set" and body.get("index") is not None):
            idx = body.get("index")
            if idx is not None and isinstance(idx, int) and 0 <= idx < len(current_list):
                if key_val:
                    current_list[idx] = key_val
                    env_vars[env_var] = ",".join(current_list)
            else:
                if key_val:
                    env_vars[env_var] = key_val
                else:
                    env_vars.pop(env_var, None)
        else:
            if key_val:
                env_vars[env_var] = key_val
            else:
                env_vars.pop(env_var, None)

        with open(_ENV_FILE, "w") as f:
            for k, v in env_vars.items():
                f.write(f"{k}={v}\n")

        reload_env()
        if _router_instance:
            _router_instance.api_keys = get_nvidia_keys()
            _router_instance.openrouter_key = get_openrouter_key()
            _router_instance.opencode_key = get_opencode_key()
            _router_instance.groq_keys = get_groq_keys()
            _router_instance.cerebras_keys = get_cerebras_keys()
            _router_instance.bai_key = get_bai_key()

        logger.success(f"Updated API keys for {provider} via Web UI.")
        return {"success": True, "provider": provider}

    @app.post("/api/settings")
    async def update_router_settings(request: Request):
        _check_auth(request)
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        for k, v in body.items():
            if k == "fallback_models":
                if isinstance(v, list):
                    cleaned = [str(m).strip() for m in v if str(m).strip()][:2]
                    update_setting("fallback_models", cleaned)
                    logger.info(f"Fallback chain updated: {cleaned}")
            else:
                update_setting(k, v)
            if k == "primary_model" and _router_instance:
                logger.info(f"Primary model updated to: {v}")
            if k == "routing_strategy" and _router_instance:
                _router_instance.strategy = str(v).strip().lower()
                logger.info(f"Routing strategy switched to: {v}")

        return {"success": True, "settings": _load_settings()}

    @app.get("/api/combos")
    async def list_combos_endpoint(request: Request):
        _check_auth(request)
        raw_combos = load_combos()
        if _router_instance and _router_instance.models:
            now = time.time()
            settings = _load_settings()
            max_lat = settings.get("max_latency_threshold", 3.0)
            models_info = []
            for m in _router_instance.models:
                mid = m.get("id")
                if mid:
                    cooling = _router_instance._rate_limited_until.get(mid, 0) > now
                    is_h = _router_instance._is_model_healthy(mid) and not cooling
                    lat = round(_router_instance._latencies.get(mid, 0.45), 3)
                    models_info.append({"id": mid, "latency": lat, "healthy": is_h})
            return {"combos": _enrich_combos(raw_combos, models_info, max_lat)}
        return {"combos": raw_combos}

    @app.post("/api/combos")
    async def create_combo_endpoint(request: Request):
        _check_auth(request)
        body = await request.json()
        name = body.get("name", "").strip()
        strategy = body.get("strategy", "fallback").strip()
        models = body.get("models", [])
        if not name:
            raise HTTPException(status_code=400, detail="Combo name is required.")
        if strategy not in ("round_robin", "fallback"):
            raise HTTPException(status_code=400, detail="strategy must be 'round_robin' or 'fallback'.")
        try:
            combo = create_combo(name, strategy, models)
            logger.success(f"Combo '{name}' created ({strategy}, {len(models)} models).")
            return {"success": True, "combo": combo}
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @app.put("/api/combos/{name}")
    async def update_combo_endpoint(name: str, request: Request):
        _check_auth(request)
        body = await request.json()
        strategy = body.get("strategy", "fallback").strip()
        models = body.get("models", [])
        try:
            combo = update_combo(name, strategy, models)
            logger.success(f"Combo '{name}' updated ({strategy}, {len(models)} models).")
            return {"success": True, "combo": combo}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.delete("/api/combos/{name}")
    async def delete_combo_endpoint(name: str, request: Request):
        _check_auth(request)
        ok = delete_combo(name)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Combo '{name}' not found.")
        logger.success(f"Combo '{name}' deleted.")
        return {"success": True}

    @app.post("/api/server/restart")
    async def restart_gateway(request: Request):
        _check_auth(request)
        import subprocess
        import shutil
        reload_env()
        if _router_instance:
            _router_instance.api_keys = get_nvidia_keys()
            _router_instance.openrouter_key = get_openrouter_key()
            _router_instance.opencode_key = get_opencode_key()
            _router_instance.groq_keys = get_groq_keys()
            _router_instance.cerebras_keys = get_cerebras_keys()
            _router_instance.bai_key = get_bai_key()
            asyncio.create_task(_router_instance.refresh_models())

        pm2_bin = shutil.which("pm2")
        if pm2_bin:
            async def _bg_restart():
                await asyncio.sleep(0.5)
                subprocess.run([pm2_bin, "restart", "nim-router", "--update-env"])
            asyncio.create_task(_bg_restart())
            logger.info("Restarting nim-router gateway via PM2...")
            return {"success": True, "message": "Gateway process restarting via PM2..."}
        
        logger.info("Gateway configuration & pool refreshed.")
        return {"success": True, "message": "Gateway reloaded successfully."}

    @app.post("/api/probe")
    async def run_live_probe(request: Request):
        _check_auth(request)
        if not _router_instance:
            raise HTTPException(status_code=500, detail="Router not initialized")

        logger.info("Executing on-demand health probe scan across providers via Web UI...")
        await _router_instance.refresh_models()

        return {
            "success": True,
            "total_discovered": len(_router_instance.models),
            "models": [
                {
                    "id": m.get("id"),
                    "provider": _router_instance._get_provider_name(m.get("id", "")),
                    "latency": round(_router_instance._latencies.get(m.get("id", ""), 0.4), 3),
                }
                for m in _router_instance.models
            ]
        }

    @app.get("/api/logs/history")
    async def get_logs_history(request: Request):
        _check_auth(request)
        return {"logs": get_recent_logs()}

    @app.get("/api/logs/stream")
    async def stream_server_logs(request: Request):
        _check_auth(request)
        q = register_log_subscriber()

        async def event_generator():
            try:
                recent = get_recent_logs()
                for entry in recent[-30:]:
                    yield f"data: {json.dumps(entry)}\n\n"

                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        entry = await asyncio.wait_for(q.get(), timeout=15.0)
                        yield f"data: {json.dumps(entry)}\n\n"
                    except asyncio.TimeoutError:
                        yield f": keep-alive\n\n"
            finally:
                unregister_log_subscriber(q)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "total_models": len(_router_instance.models) if _router_instance else 0,
            "healthy_pool_size": len(_router_instance._healthy_pool) if _router_instance else 0
        }

    @app.get("/models")
    @app.get("/v1/models")
    @app.get("/api/v1/models")
    @app.get("/api/models")
    async def list_models(task: Optional[str] = None):
        if not _router_instance:
            return {"error": "Router not initialized"}

        categories = [
            ("nim-auto", "nim-router"),
            ("nim-tools", "nim-router"),
            ("nim-coding", "nim-router"),
            ("nim-reasoning", "nim-router"),
            ("nim-vision", "nim-router"),
            ("nim-moe", "nim-router"),
            ("nim-chat", "nim-router"),
        ]

        data = []
        added_ids = set()

        for cat_id, owner in categories:
            added_ids.add(cat_id)
            data.append({"id": cat_id, "object": "model", "owned_by": owner})

        for combo in load_combos():
            cname = combo.get("name")
            if cname and cname not in added_ids:
                added_ids.add(cname)
                data.append({"id": cname, "object": "model", "owned_by": "nim-router-combo"})

        target_task = (task or "").strip().lower()

        for m in _router_instance.models:
            mid = m.get("id")
            if mid and mid not in added_ids and " " not in mid:
                prov = _router_instance._get_provider_name(mid)
                if target_task:
                    caps = get_model_capabilities(mid, prov, m)
                    if not caps.get(target_task, False):
                        continue
                added_ids.add(mid)
                data.append({"id": mid, "object": "model", "owned_by": prov.lower()})

        return {"object": "list", "data": data}

    @app.get("/v1/models/{model_id:path}")
    @app.get("/models/{model_id:path}")
    @app.get("/api/v1/models/{model_id:path}")
    @app.get("/api/models/{model_id:path}")
    async def get_model(model_id: str):
        clean_id = model_id.strip()
        for prefix in ("[NVIDIA] ", "[OpenRouter] ", "[OpenCode] ", "[Groq] ", "[Cerebras] ", "[BAI] ", "[Category] "):
            if clean_id.startswith(prefix):
                clean_id = clean_id[len(prefix):].strip()
        provider = _router_instance._get_provider_name(clean_id) if _router_instance else "nim-router"
        return {"id": model_id, "object": "model", "owned_by": provider.lower()}

    @app.get("/api/tags")
    async def get_tags():
        if not _router_instance:
            return {"models": []}

        categories = [
            "nim-auto",
            "nim-tools",
            "nim-coding",
            "nim-reasoning",
            "nim-vision",
            "nim-moe",
            "nim-chat",
        ]
        tags = []
        added_names = set()

        for cat_name in categories:
            added_names.add(cat_name)
            tags.append({"name": cat_name, "model": cat_name, "modified_at": "2026-08-30T00:00:00Z", "size": 0})

        for m in _router_instance.models:
            mid = m.get("id")
            if mid and mid not in added_names and " " not in mid:
                added_names.add(mid)
                tags.append({"name": mid, "model": mid, "modified_at": "2026-08-30T00:00:00Z", "size": 0})

        return {"models": tags}

    @app.post("/api/show")
    @app.post("/show")
    async def show_model_details(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        model_name = body.get("name") or body.get("model") or "nim-auto"
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
    async def refresh_models(request: Request, sync: bool = False):
        if not _router_instance:
            raise HTTPException(status_code=500, detail="Router not initialized")
        reload_env()
        try:
            body = await request.json()
            if isinstance(body, dict) and "primary_model" in body:
                val = str(body["primary_model"]).strip()
                if val:
                    update_setting("primary_model", val)
        except Exception:
            pass
        _router_instance.api_keys = get_nvidia_keys()
        _router_instance.openrouter_key = get_openrouter_key()
        _router_instance.opencode_key = get_opencode_key()
        _router_instance.groq_keys = get_groq_keys()
        _router_instance.cerebras_keys = get_cerebras_keys()
        _router_instance.bai_key = get_bai_key()
        if sync:
            await _router_instance.refresh_models()
        else:
            asyncio.create_task(_router_instance.refresh_models())
        return {
            "message": "Models refreshed successfully",
            "primary_model": get_primary_model(),
            "working_models": len(_router_instance.models),
            "models": [m.get("id") for m in _router_instance.models if m.get("id")]
        }

    @app.post("/v1/chat/completions")
    @app.post("/chat/completions")
    @app.post("/api/v1/chat/completions")
    @app.post("/api/chat/completions")
    async def chat_completions(request: Request):
        return await _router_instance.handle_request(request)

    base_dir = os.path.dirname(os.path.dirname(__file__))
    dist_dir = os.path.join(base_dir, "frontend", "dist")
    assets_dir = os.path.join(dist_dir, "assets")

    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/favicon.ico")
    @app.get("/favicon.svg")
    async def serve_favicon():
        fav_path = os.path.join(dist_dir, "favicon.svg")
        if os.path.exists(fav_path):
            return FileResponse(fav_path, media_type="image/svg+xml")
        fallback_fav = os.path.join(base_dir, "frontend", "icons", "nim-cube.svg")
        if os.path.exists(fallback_fav):
            return FileResponse(fallback_fav, media_type="image/svg+xml")
        return Response(status_code=404)

    @app.get("/")
    @app.get("/ui")
    @app.get("/dashboard")
    async def serve_index():
        index_path = os.path.join(dist_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        fallback_html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>NIM Router - Dashboard Build Required</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f1117; color: #e2e8f0; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; }
    .card { background: #1a1f2c; border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 32px; max-width: 540px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.5); }
    h1 { color: #00d2ff; font-size: 22px; margin-bottom: 12px; }
    p { color: #94a3b8; font-size: 14px; line-height: 1.6; margin-bottom: 24px; }
    code { background: rgba(0,210,255,0.1); color: #00f5a0; padding: 3px 8px; border-radius: 6px; font-family: monospace; font-size: 13px; }
    .box { background: #0b0d13; border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; padding: 14px; text-align: left; font-family: monospace; font-size: 13px; color: #38bdf8; margin-bottom: 20px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Web Dashboard Build Required</h1>
    <p>The NIM Router gateway is running, but the frontend distribution assets were not found in <code>frontend/dist/</code>.</p>
    <div class="box">
      $ nim build<br>
      $ cd frontend &amp;&amp; npm install &amp;&amp; npm run build
    </div>
    <p style="margin-bottom:0; font-size: 12px; color: #64748b;">Once built, reload this page to access the full web dashboard.</p>
  </div>
</body>
</html>"""
        return HTMLResponse(content=fallback_html, status_code=200)

    return app

