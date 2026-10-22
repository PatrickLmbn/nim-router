import asyncio
import json
import sys
import time
import anyio
import httpx
from fastapi import HTTPException, Response
from fastapi.responses import StreamingResponse

from nim_router.config import (
    NIM_API_BASE,
    OPENROUTER_API_BASE,
    OPENCODE_API_BASE,
    GROQ_API_BASE,
    CEREBRAS_API_BASE,
    BAI_API_BASE,
    get_first_token_timeout,
    get_stream_idle_timeout,
)
from nim_router.logger import logger
from nim_router.schemas import ChatCompletionRequest
from nim_router.catalog import is_banned_model, load_fallback_models
from nim_router.kiro import KiroClient, KiroAuth, resolve_refresh_token, kiro_upstream_model_id
from nim_router.antigravity import (
    AntigravityClient,
    AntigravityAuth,
    antigravity_upstream_model_id,
)
from nim_router.antigravity import resolve_refresh_token as resolve_antigravity_refresh_token

import email.utils
from typing import Callable, Optional
from nim_router.classifier import estimate_token_count

_shared_client: httpx.AsyncClient | None = None
_active_streams: int = 0

def get_shared_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        limits = httpx.Limits(max_connections=200, max_keepalive_connections=50, keepalive_expiry=30)
        timeout = httpx.Timeout(connect=15.0, read=300.0, write=60.0, pool=60.0)
        _shared_client = httpx.AsyncClient(limits=limits, timeout=timeout)
    return _shared_client

def get_active_stream_count() -> int:
    return _active_streams

_kiro_auth: KiroAuth | None = None
_kiro_client: KiroClient | None = None

def get_kiro_client() -> tuple[KiroClient, KiroAuth]:
    global _kiro_auth, _kiro_client
    if _kiro_client is None or _kiro_auth is None:
        token = resolve_refresh_token()
        _kiro_auth = KiroAuth(token)
        _kiro_client = KiroClient(_kiro_auth)
    return _kiro_client, _kiro_auth

def set_kiro_refresh_token(token: str) -> bool:
    global _kiro_auth, _kiro_client
    token = (token or "").strip()
    if not token:
        if _kiro_auth is None:
            return False
        _kiro_auth.refresh_token = ""
        _kiro_auth.access_token = ""
        _kiro_auth.expires_at = 0.0
        return True
    if _kiro_auth is None:
        _kiro_auth = KiroAuth(token)
        _kiro_client = KiroClient(_kiro_auth)
        return True
    if _kiro_auth.refresh_token == token:
        return False
    _kiro_auth.refresh_token = token
    _kiro_auth.access_token = ""
    _kiro_auth.expires_at = 0.0
    return True

_antigravity_auth: AntigravityAuth | None = None
_antigravity_client: AntigravityClient | None = None

def get_antigravity_client() -> tuple[AntigravityClient, AntigravityAuth]:
    global _antigravity_auth, _antigravity_client
    if _antigravity_client is None or _antigravity_auth is None:
        token = resolve_antigravity_refresh_token()
        _antigravity_auth = AntigravityAuth(token)
        _antigravity_client = AntigravityClient(_antigravity_auth)
    return _antigravity_client, _antigravity_auth

def set_antigravity_refresh_token(token: str) -> bool:
    global _antigravity_auth, _antigravity_client
    token = (token or "").strip()
    if not token:
        if _antigravity_auth is None:
            return False
        _antigravity_auth.refresh_token = ""
        _antigravity_auth.access_token = ""
        _antigravity_auth.expires_at = 0.0
        return True
    if _antigravity_auth is None:
        _antigravity_auth = AntigravityAuth(token)
        _antigravity_client = AntigravityClient(_antigravity_auth)
        return True
    if _antigravity_auth.refresh_token == token:
        return False
    _antigravity_auth.refresh_token = token
    _antigravity_auth.access_token = ""
    _antigravity_auth.expires_at = 0.0
    return True

async def close_shared_client():
    global _shared_client
    if _shared_client and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None

async def _safe_aclose(response) -> None:
    if response is None:
        return
    try:
        await response.aclose()
    except asyncio.CancelledError:
        try:
            with anyio.CancelScope(shield=True):
                await response.aclose()
        except Exception:
            pass
        raise
    except Exception:
        pass

def parse_retry_after(header_val: str | None) -> float | None:
    if not header_val:
        return None
    header_val = str(header_val).strip()
    if not header_val:
        return None
    try:
        val = float(header_val)
        return max(0.0, val)
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(header_val)
        if dt:
            diff = dt.timestamp() - time.time()
            return max(0.0, diff)
    except Exception:
        pass
    return None

async def probe_model(api_key: str, client: httpx.AsyncClient, model_id: str, sem: asyncio.Semaphore, base_url: str = NIM_API_BASE, probe_endpoint: str = "chat/completions", timeout_sec: float = 8.0) -> tuple[bool, float]:
    if is_banned_model(model_id):
        return False, 999.0
    async with sem:
        t0 = time.time()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        if "openrouter.ai" in base_url:
            headers["HTTP-Referer"] = "https://github.com/patricklmbn/nim-router"
            headers["X-Title"] = "NIM Router"
        try:
            if probe_endpoint == "systemone":
                payload = {
                    "model": model_id,
                    "state": "",
                    "questions": {}
                }
            elif probe_endpoint == "responses":
                payload = {
                    "model": model_id,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 5,
                    "temperature": 0.0
                }
            else:
                payload = {
                    "model": model_id,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 5,
                    "temperature": 0.0
                }
            resp = await client.post(
                f"{base_url.rstrip('/')}/{probe_endpoint}",
                headers=headers,
                json=payload,
                timeout=timeout_sec
            )
            elapsed = round(time.time() - t0, 3)
            if resp.status_code == 200:
                return True, elapsed
            elif resp.status_code in (400, 429, 500, 502, 503):
                return True, 10.0 + elapsed
            else:
                return False, 999.0
        except Exception:
            return False, 999.0

async def discover_kiro_models(
    latencies_dict: dict,
    kiro_refresh_token: str = "",
    verify: bool = True,
) -> list[dict]:
    kiro_client, kiro_auth = get_kiro_client()
    if kiro_refresh_token:
        kiro_auth.refresh_token = kiro_refresh_token.strip()
    if not kiro_auth.configured:
        logger.info("Kiro probe skipped: no refresh token configured.")
        return []

    catalogue = await kiro_client.list_models()
    discovered: list[dict] = []
    for model in catalogue:
        mid = model.get("id")
        if not mid or is_banned_model(mid):
            continue
        discovered.append(model)

    if not verify:
        return discovered

    verified: list[dict] = []
    for model in discovered:
        mid = model.get("id", "")
        try:
            t0 = time.time()
            result = await asyncio.wait_for(
                kiro_client.create_chat_completion(
                    model_id=mid,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=8,
                ),
                timeout=45.0,
            )
            elapsed = round(time.time() - t0, 3)
            if result.get("choices"):
                latencies_dict[mid] = elapsed
                verified.append(model)
        except Exception as e:
            logger.warning(f"Kiro model {mid} failed probe: {e}")

    logger.success(f"Kiro: {len(verified)}/{len(discovered)} models verified.")
    return verified


async def discover_antigravity_models(
    latencies_dict: dict,
    antigravity_refresh_token: str = "",
    verify: bool = True,
) -> list[dict]:
    antigravity_client, antigravity_auth = get_antigravity_client()
    if antigravity_refresh_token:
        antigravity_auth.refresh_token = antigravity_refresh_token.strip()
    if not antigravity_auth.configured:
        logger.info("Antigravity probe skipped: no refresh token configured.")
        return []

    catalogue = await antigravity_client.list_models()
    discovered: list[dict] = []
    for model in catalogue:
        mid = model.get("id")
        if not mid or is_banned_model(mid):
            continue
        discovered.append(model)

    if not verify:
        return discovered

    verified: list[dict] = []
    for model in discovered:
        mid = model.get("id", "")
        try:
            t0 = time.time()
            result = await asyncio.wait_for(
                antigravity_client.create_chat_completion(
                    model_id=mid,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=8,
                ),
                timeout=45.0,
            )
            elapsed = round(time.time() - t0, 3)
            if result.get("choices"):
                latencies_dict[mid] = elapsed
                verified.append(model)
        except Exception as e:
            logger.warning(f"Antigravity model {mid} failed probe: {e}")

    logger.success(f"Antigravity: {len(verified)}/{len(discovered)} models verified.")
    return verified


async def discover_models(api_keys: list[str] | str, latencies_dict: dict, openrouter_keys: list[str] | str = "", opencode_key: str = "", groq_keys: list[str] | str = "", cerebras_keys: list[str] | str = "", bai_key: str = "", kiro_refresh_token: str = "", antigravity_refresh_token: str = "") -> list[dict]:
    primary_nvidia_key = api_keys[0] if isinstance(api_keys, list) and api_keys else (api_keys if isinstance(api_keys, str) else "")
    primary_groq_key = groq_keys[0] if isinstance(groq_keys, list) and groq_keys else (groq_keys if isinstance(groq_keys, str) else "")
    primary_cerebras_key = cerebras_keys[0] if isinstance(cerebras_keys, list) and cerebras_keys else (cerebras_keys if isinstance(cerebras_keys, str) else "")
    openrouter_keys_list = [k.strip() for k in openrouter_keys if k.strip()] if isinstance(openrouter_keys, list) else [k.strip() for k in (openrouter_keys or "").split(",") if k.strip()]
    primary_openrouter_key = openrouter_keys_list[0] if openrouter_keys_list else ""

    all_discovered = []
    candidates_to_probe = []

    if primary_nvidia_key:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{NIM_API_BASE}/models",
                    headers={"Authorization": f"Bearer {primary_nvidia_key}"},
                )
                if response.status_code == 200:
                    data = response.json()
                    all_models = data.get("data", [])
                    valid_models = [
                        m for m in all_models
                        if m.get("id") and not is_banned_model(m.get("id"))
                    ]
                    for m in valid_models:
                        m_copy = dict(m)
                        m_copy["provider"] = "NVIDIA"
                        candidates_to_probe.append((primary_nvidia_key, m_copy, NIM_API_BASE))
        except Exception as e:
            logger.error(f"NVIDIA model discovery failed: {e}")

    if primary_openrouter_key:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{OPENROUTER_API_BASE}/models",
                    headers={"Authorization": f"Bearer {primary_openrouter_key}"},
                )
                if response.status_code == 200:
                    data = response.json()
                    or_models = [
                        m for m in data.get("data", [])
                        if (
                            m.get("id", "").endswith(":free")
                            or (
                                m.get("pricing")
                                and (
                                    m["pricing"].get("prompt") in ("0", "0.0", 0)
                                    and m["pricing"].get("completion") in ("0", "0.0", 0)
                                )
                            )
                        )
                    ]
                    for m in or_models:
                        m_copy = dict(m)
                        m_copy["provider"] = "OpenRouter"
                        for or_key in openrouter_keys_list:
                            candidates_to_probe.append((or_key, m_copy, OPENROUTER_API_BASE))
        except Exception as e:
            logger.error(f"OpenRouter discovery failed: {e}")

    if opencode_key:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{OPENCODE_API_BASE}/models",
                    headers={"Authorization": f"Bearer {opencode_key}"},
                )
                if response.status_code == 200:
                    data = response.json()
                    oc_models = [
                        m for m in data.get("data", [])
                        if "free" in m.get("id", "").lower() and not is_banned_model(m.get("id", ""))
                    ]
                    for m in oc_models:
                        m_copy = dict(m)
                        m_copy["provider"] = "OpenCode"
                        candidates_to_probe.append((opencode_key, m_copy, OPENCODE_API_BASE))
        except Exception as e:
            logger.error(f"OpenCode discovery failed: {e}")

    if primary_groq_key:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{GROQ_API_BASE}/models",
                    headers={"Authorization": f"Bearer {primary_groq_key}"},
                )
                if response.status_code == 200:
                    data = response.json()
                    groq_models = [
                        m for m in data.get("data", [])
                        if m.get("id") and not is_banned_model(m.get("id")) and "whisper" not in m.get("id", "").lower()
                    ]
                    for m in groq_models:
                        m_copy = dict(m)
                        m_copy["provider"] = "Groq"
                        candidates_to_probe.append((primary_groq_key, m_copy, GROQ_API_BASE))
        except Exception as e:
            logger.error(f"Groq model discovery failed: {e}")

    if primary_cerebras_key:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{CEREBRAS_API_BASE}/models",
                    headers={"Authorization": f"Bearer {primary_cerebras_key}"},
                )
                if response.status_code == 200:
                    data = response.json()
                    cerebras_models = [
                        m for m in data.get("data", [])
                        if m.get("id") and not is_banned_model(m.get("id"))
                    ]
                    for m in cerebras_models:
                        m_copy = dict(m)
                        m_copy["provider"] = "Cerebras"
                        candidates_to_probe.append((primary_cerebras_key, m_copy, CEREBRAS_API_BASE))
        except Exception as e:
            logger.error(f"Cerebras model discovery failed: {e}")

    if bai_key:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{BAI_API_BASE}/models",
                    headers={"Authorization": f"Bearer {bai_key}"},
                )
                if response.status_code == 200:
                    data = response.json()
                    bai_free_set = {"glm-5.3-flash", "qwen3.8-flash", "hy3"}
                    bai_models = [
                        m for m in data.get("data", [])
                        if m.get("id") in bai_free_set and not is_banned_model(m.get("id"))
                    ]
                    for m in bai_models:
                        m_copy = dict(m)
                        m_copy["provider"] = "BAI"
                        candidates_to_probe.append((bai_key, m_copy, BAI_API_BASE))
        except Exception as e:
            logger.error(f"BAI model discovery failed: {e}")

    kiro_discovered: list[dict] = []
    try:
        kiro_discovered = await discover_kiro_models(
            latencies_dict, kiro_refresh_token, verify=False
        )
    except Exception as e:
        logger.error(f"Kiro model discovery failed: {e}")

    antigravity_discovered: list[dict] = []
    try:
        antigravity_discovered = await discover_antigravity_models(
            latencies_dict, antigravity_refresh_token, verify=False
        )
    except Exception as e:
        logger.error(f"Antigravity model discovery failed: {e}")

    if candidates_to_probe:
        total_probes = len(candidates_to_probe)
        completed_count = 0
        lock = asyncio.Lock()
        sem = asyncio.Semaphore(15)
        is_tty = sys.stdout.isatty()

        logger.info(f"Discovered {total_probes} candidate models across enabled providers.")

        async with httpx.AsyncClient(timeout=30) as client:
            async def probe_task(item):
                nonlocal completed_count
                key, m_obj, base_url = item
                mid = m_obj.get("id", "")
                try:
                    ok, latency = await asyncio.wait_for(probe_model(key, client, mid, sem, base_url, timeout_sec=8.0), timeout=10.0)
                except Exception:
                    ok, latency = False, 999.0
                async with lock:
                    completed_count += 1
                    if is_tty:
                        pct = int((completed_count / total_probes) * 100) if total_probes else 100
                        bar_len = 30
                        filled = int((completed_count / total_probes) * bar_len) if total_probes else bar_len
                        filled_bar = "=" * filled
                        empty_bar = "-" * (bar_len - filled)
                        sys.stdout.write(f"\r\033[1;36mProbing active model endpoints:\033[0m \033[90m[\033[1;32m{filled_bar}\033[90m{empty_bar}]\033[0m \033[1;37m{completed_count}/{total_probes}\033[0m \033[1;33m({pct}%)\033[0m")
                        sys.stdout.flush()

                return m_obj, ok, latency

            probe_results = await asyncio.gather(*[probe_task(item) for item in candidates_to_probe])
            if is_tty:
                sys.stdout.write("\n")
                sys.stdout.flush()

            for m, ok, latency in probe_results:
                mid = m.get("id")
                if ok and mid:
                    latencies_dict[mid] = latency
                    all_discovered.append(m)

    if kiro_discovered:
        kiro_verified = await discover_kiro_models(
            latencies_dict, kiro_refresh_token, verify=True
        )
        all_discovered.extend(kiro_verified)

    if antigravity_discovered:
        antigravity_verified = await discover_antigravity_models(
            latencies_dict, antigravity_refresh_token, verify=True
        )
        all_discovered.extend(antigravity_verified)

    if not all_discovered:
        all_discovered = load_fallback_models(latencies_dict)
        for m in all_discovered:
            if "provider" not in m:
                m["provider"] = "NVIDIA"

    all_discovered.sort(key=lambda m: latencies_dict.get(m.get("id", ""), 999.0))
    logger.success(f"Multi-provider model discovery complete: {len(all_discovered)} active models in pool.")
    return all_discovered

def _looks_degenerate(text: str) -> bool:
    if len(text) < 400:
        return False
    ws = sum(1 for ch in text if ch.isspace())
    if ws / len(text) > 0.02:
        return False
    b64 = sum(1 for ch in text if ch.isalnum() or ch in "+/=_-")
    return b64 / len(text) > 0.92


async def call_provider_endpoint(
    api_key: str,
    model_id: str,
    request: ChatCompletionRequest,
    base_url: str = NIM_API_BASE,
    on_usage: Optional[Callable[[int, int, int, bool, bool], None]] = None
) -> Response:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if "openrouter.ai" in base_url:
        headers["HTTP-Referer"] = "https://github.com/patricklmbn/nim-router"
        headers["X-Title"] = "NIM Router"

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
        if "api.b.ai" in base_url and payload["max_tokens"] <= 2:
            payload["max_tokens"] = 3
    if request.stop is not None:
        payload["stop"] = request.stop
    if request.tools is not None:
        payload["tools"] = request.tools

    if request.stream:
        if any(k in base_url for k in ("groq.com", "cerebras.ai", "openrouter.ai")):
            payload["stream_options"] = {"include_usage": True}

    client = get_shared_client()

    if request.stream:
        response = None
        handed_off = False
        first_token_timeout = get_first_token_timeout()
        idle_timeout = get_stream_idle_timeout()
        try:
            req = client.build_request("POST", url, headers=headers, json=payload)
            response = await asyncio.wait_for(
                client.send(req, stream=True), timeout=first_token_timeout
            )

            if response.status_code == 200:
                aiter = response.aiter_raw()
                first_chunk = None
                try:
                    first_chunk = await asyncio.wait_for(
                        aiter.__anext__(), timeout=first_token_timeout
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        f"No first token from {model_id} within {first_token_timeout:.0f}s, failing over..."
                    )
                    raise HTTPException(
                        status_code=504,
                        detail=f"Upstream model {model_id} accepted the request but produced no output within {first_token_timeout:.0f}s.",
                    )
                except StopAsyncIteration:
                    logger.warning(
                        f"Model {model_id} returned an empty 200 response (no chunks), failing over..."
                    )
                    raise HTTPException(
                        status_code=503,
                        detail=f"Upstream model {model_id} returned an empty response with no content chunks.",
                    )

                if first_chunk:
                    sample = first_chunk.decode("utf-8", errors="ignore")
                    if '"error":' in sample and ('"message":' in sample or '"code":' in sample):
                        detail_msg = sample
                        try:
                            clean = sample.strip()
                            if clean.startswith("data:"):
                                clean = clean[5:].strip()
                            data = json.loads(clean)
                            detail_msg = data.get("error", {}).get("message", sample)
                        except Exception:
                            pass
                        raise HTTPException(status_code=503, detail=detail_msg)

                stream_prompt_tokens = 0
                stream_comp_tokens = 0
                stream_total_tokens = 0
                has_exact_usage = False
                collected_chars = 0
                sse_buffer = ""
                stream_sample = []
                stream_sample_chars = 0
                has_visible_content = False
                has_reasoning_content = False

                def process_chunk_text(text: str):
                    nonlocal sse_buffer, stream_prompt_tokens, stream_comp_tokens, stream_total_tokens, has_exact_usage, collected_chars, has_visible_content, has_reasoning_content, stream_sample_chars
                    sse_buffer += text
                    lines = sse_buffer.split("\n")
                    sse_buffer = lines[-1]
                    for line in lines[:-1]:
                        clean_line = line.strip()
                        if not clean_line.startswith("data:"):
                            continue
                        data_body = clean_line[5:].strip()
                        if not data_body or data_body == "[DONE]":
                            continue
                        try:
                            chunk_data = json.loads(data_body)
                            usage_data = chunk_data.get("usage")
                            if usage_data and isinstance(usage_data, dict):
                                p = usage_data.get("prompt_tokens") or 0
                                c = usage_data.get("completion_tokens") or 0
                                t = usage_data.get("total_tokens") or (p + c)
                                if t > 0:
                                    stream_prompt_tokens = p
                                    stream_comp_tokens = c
                                    stream_total_tokens = t
                                    has_exact_usage = True
                            choices = chunk_data.get("choices") or []
                            for choice in choices:
                                delta = choice.get("delta") or {}
                                vis = delta.get("content") or ""
                                if vis:
                                    has_visible_content = True
                                    if stream_sample_chars < 4000:
                                        stream_sample.append(vis)
                                        stream_sample_chars += len(vis)
                                reasoning = delta.get("reasoning_content") or ""
                                if reasoning:
                                    has_reasoning_content = True
                                if delta.get("tool_calls"):
                                    has_visible_content = True
                                content = vis or reasoning
                                if content:
                                    collected_chars += len(content)
                        except Exception:
                            pass

                async def stream_generator():
                    global _active_streams
                    _active_streams += 1
                    try:
                        if first_chunk:
                            process_chunk_text(first_chunk.decode("utf-8", errors="ignore"))
                            yield first_chunk
                        while True:
                            try:
                                chunk = await asyncio.wait_for(
                                    aiter.__anext__(), timeout=idle_timeout
                                )
                            except StopAsyncIteration:
                                break
                            except asyncio.TimeoutError:
                                logger.warning(
                                    f"Stream stalled for {model_id}: no data for {idle_timeout:.0f}s, closing."
                                )
                                err_msg = json.dumps({
                                    "error": {
                                        "message": f"Stream connection stalled from upstream model ({model_id}) for {idle_timeout:.0f}s.",
                                        "type": "upstream_timeout",
                                        "code": 504
                                    }
                                })
                                yield f"data: {err_msg}\n\n".encode("utf-8")
                                break
                            process_chunk_text(chunk.decode("utf-8", errors="ignore"))
                            yield chunk
                    except (httpx.ReadTimeout, httpx.RequestError) as e:
                        logger.warning(f"Stream read timeout/error for {model_id}: {e}")
                        err_msg = json.dumps({
                            "error": {
                                "message": f"Stream connection timed out from upstream model ({model_id}).",
                                "type": "upstream_timeout",
                                "code": 504
                            }
                        })
                        yield f"data: {err_msg}\n\n".encode("utf-8")
                    finally:
                        _active_streams = max(0, _active_streams - 1)
                        await _safe_aclose(response)
                        if sse_buffer:
                            process_chunk_text("\n")
                        final_prompt = stream_prompt_tokens
                        final_comp = stream_comp_tokens
                        final_total = stream_total_tokens
                        is_est = not has_exact_usage
                        if is_est:
                            final_prompt = estimate_token_count(request)
                            final_comp = max(1, int(collected_chars / 3.8)) if collected_chars > 0 else 0
                            final_total = final_prompt + final_comp
                        degraded = (not has_visible_content and not has_reasoning_content) or _looks_degenerate("".join(stream_sample))
                        if on_usage:
                            try:
                                on_usage(final_prompt, final_comp, final_total, is_est, degraded)
                            except Exception:
                                pass

                handed_off = True
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
                retry_sec = parse_retry_after(response.headers.get("Retry-After") or response.headers.get("retry-after"))

                try:
                    err_data = json.loads(body.decode())
                    detail = err_data.get("error", {}).get("message", str(err_data))
                    if retry_sec is None:
                        err_retry = err_data.get("error", {}).get("retry_after") or err_data.get("retry_after")
                        if err_retry is not None:
                            try:
                                retry_sec = float(err_retry)
                            except (ValueError, TypeError):
                                pass
                except Exception:
                    detail = body.decode()

                resp_headers = {"Retry-After": str(retry_sec)} if retry_sec is not None else None
                raise HTTPException(status_code=response.status_code, detail=detail, headers=resp_headers)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))
        finally:
            if response is not None and not handed_off:
                await _safe_aclose(response)
    else:
        try:
            response = await client.post(url, headers=headers, json=payload)
            retry_sec = parse_retry_after(response.headers.get("Retry-After") or response.headers.get("retry-after"))

            if response.status_code == 200:
                extracted_usage = None
                degraded = False
                try:
                    resp_json = response.json()
                    usage_obj = resp_json.get("usage")
                    if usage_obj and isinstance(usage_obj, dict):
                        p_tok = usage_obj.get("prompt_tokens") or 0
                        c_tok = usage_obj.get("completion_tokens") or 0
                        t_tok = usage_obj.get("total_tokens") or (p_tok + c_tok)
                        extracted_usage = (p_tok, c_tok, t_tok, False)
                    else:
                        est_p = estimate_token_count(request)
                        comp_text = ""
                        for c in resp_json.get("choices", []):
                            comp_text += c.get("message", {}).get("content", "") or ""
                        est_c = max(1, int(len(comp_text) / 3.8)) if comp_text else 0
                        extracted_usage = (est_p, est_c, est_p + est_c, True)

                    choices = resp_json.get("choices", [])
                    visible_text = ""
                    has_tool_calls = False
                    for c in choices:
                        msg_obj = c.get("message", {})
                        if msg_obj.get("tool_calls"):
                            has_tool_calls = True
                        visible_text += msg_obj.get("content") or msg_obj.get("reasoning_content") or msg_obj.get("reasoning") or ""
                    degraded = not has_tool_calls and (
                        not choices or not visible_text.strip() or _looks_degenerate(visible_text)
                    )
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

                    usage_dispatched = False
                    if on_usage and extracted_usage:
                        try:
                            on_usage(*extracted_usage, degraded)
                            usage_dispatched = True
                        except Exception:
                            pass

                    if modified:
                        return Response(content=json.dumps(resp_json), media_type="application/json", status_code=200)
                except Exception as e:
                    logger.debug(f"Response normalization error: {e}")

                if on_usage and extracted_usage and not usage_dispatched:
                    try:
                        on_usage(*extracted_usage, degraded)
                    except Exception:
                        pass

                return Response(content=response.text, media_type="application/json", status_code=200)
            else:
                try:
                    err_data = response.json()
                    detail = err_data.get("error", {}).get("message", str(err_data))
                    if retry_sec is None:
                        err_retry = err_data.get("error", {}).get("retry_after") or err_data.get("retry_after")
                        if err_retry is not None:
                            try:
                                retry_sec = float(err_retry)
                            except (ValueError, TypeError):
                                pass
                except Exception:
                    detail = response.text or f"API error: {response.status_code}"

                resp_headers = {"Retry-After": str(retry_sec)} if retry_sec is not None else None
                raise HTTPException(status_code=response.status_code, detail=detail, headers=resp_headers)
        except httpx.RequestError as e:
            logger.error(f"Request error calling API for {model_id}: {e}")
            raise HTTPException(status_code=502, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to call API for {model_id}: {e}")
            raise HTTPException(status_code=502, detail=str(e))


async def call_kiro_endpoint(
    model_id: str,
    request: ChatCompletionRequest,
    on_usage: Optional[Callable[[int, int, int, bool, bool], None]] = None
) -> Response:
    kiro_client, auth = get_kiro_client()
    if not auth.configured:
        raise HTTPException(
            status_code=503,
            detail="Kiro is not configured. Set KIRO_REFRESH_TOKEN or sign in with the Kiro CLI.",
        )

    client = get_shared_client()

    try:
        if request.stream:
            async def stream_generator():
                global _active_streams
                _active_streams += 1
                prompt_tokens = 0
                completion_tokens = 0
                has_visible_content = False
                collected_chars = 0
                try:
                    async for chunk in kiro_client.stream_chat_completion(
                        model_id=model_id,
                        messages=request.messages,
                        tools=request.tools,
                        temperature=request.temperature,
                        max_tokens=request.max_tokens,
                        client=client,
                    ):
                        text = chunk.decode("utf-8", errors="ignore")
                        if '"usage"' in text and '"choices": []' in text:
                            try:
                                payload = json.loads(text[5:].strip())
                                usage = payload.get("usage") or {}
                                prompt_tokens = usage.get("prompt_tokens") or 0
                                completion_tokens = usage.get("completion_tokens") or 0
                            except Exception:
                                pass
                        if '"content"' in text:
                            has_visible_content = True
                            collected_chars += len(text)
                        yield chunk
                except (httpx.ReadTimeout, httpx.RequestError) as e:
                    logger.warning(f"Kiro stream read error for {model_id}: {e}")
                    raise HTTPException(status_code=504, detail=f"Stream connection timed out from Kiro model ({model_id}).")
                except Exception as e:
                    logger.error(f"Kiro stream error for {model_id}: {e}")
                    raise HTTPException(status_code=502, detail=f"Kiro stream failed for {model_id}: {e}")
                finally:
                    _active_streams = max(0, _active_streams - 1)
                    if on_usage:
                        try:
                            total = prompt_tokens + completion_tokens
                            on_usage(prompt_tokens, completion_tokens, total, True, not has_visible_content)
                        except Exception:
                            pass

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

        result = await kiro_client.create_chat_completion(
            model_id=model_id,
            messages=request.messages,
            tools=request.tools,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            client=client,
        )
        usage = result.get("usage") or {}
        if on_usage:
            try:
                on_usage(
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    usage.get("total_tokens", 0),
                    True,
                    False,
                )
            except Exception:
                pass
        return Response(content=json.dumps(result), media_type="application/json", status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Kiro request failed for {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Kiro request failed: {e}")


async def call_antigravity_endpoint(
    model_id: str,
    request: ChatCompletionRequest,
    on_usage: Optional[Callable[[int, int, int, bool, bool], None]] = None
) -> Response:
    antigravity_client, auth = get_antigravity_client()
    if not auth.configured:
        raise HTTPException(
            status_code=503,
            detail="Antigravity is not configured. Set ANTIGRAVITY_REFRESH_TOKEN or sign in with Google.",
        )

    client = get_shared_client()

    try:
        if request.stream:
            async def stream_generator():
                global _active_streams
                _active_streams += 1
                prompt_tokens = 0
                completion_tokens = 0
                has_visible_content = False
                try:
                    async for chunk in antigravity_client.stream_chat_completion(
                        model_id=model_id,
                        messages=request.messages,
                        tools=request.tools,
                        temperature=request.temperature,
                        max_tokens=request.max_tokens,
                        client=client,
                    ):
                        text = chunk.decode("utf-8", errors="ignore")
                        if '"usage"' in text and '"choices": []' in text:
                            try:
                                payload = json.loads(text[5:].strip())
                                usage = payload.get("usage") or {}
                                prompt_tokens = usage.get("prompt_tokens") or 0
                                completion_tokens = usage.get("completion_tokens") or 0
                            except Exception:
                                pass
                        if '"content"' in text:
                            has_visible_content = True
                        yield chunk
                except (httpx.ReadTimeout, httpx.RequestError) as e:
                    logger.warning(f"Antigravity stream read error for {model_id}: {e}")
                    raise HTTPException(status_code=504, detail=f"Stream connection timed out from Antigravity model ({model_id}).")
                except Exception as e:
                    logger.error(f"Antigravity stream error for {model_id}: {e}")
                    raise HTTPException(status_code=502, detail=f"Antigravity stream failed for {model_id}: {e}")
                finally:
                    _active_streams = max(0, _active_streams - 1)
                    if on_usage:
                        try:
                            total = prompt_tokens + completion_tokens
                            on_usage(prompt_tokens, completion_tokens, total, True, not has_visible_content)
                        except Exception:
                            pass

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

        result = await antigravity_client.create_chat_completion(
            model_id=model_id,
            messages=request.messages,
            tools=request.tools,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            client=client,
        )
        usage = result.get("usage") or {}
        if on_usage:
            try:
                on_usage(
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    usage.get("total_tokens", 0),
                    True,
                    False,
                )
            except Exception:
                pass
        return Response(content=json.dumps(result), media_type="application/json", status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Antigravity request failed for {model_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Antigravity request failed: {e}")
