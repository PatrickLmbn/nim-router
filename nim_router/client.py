import asyncio
import json
import sys
import time
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
)
from nim_router.logger import logger
from nim_router.schemas import ChatCompletionRequest
from nim_router.catalog import is_banned_model, load_fallback_models

import email.utils

_shared_client: httpx.AsyncClient | None = None

def get_shared_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        limits = httpx.Limits(max_connections=100, max_keepalive_connections=30, keepalive_expiry=30)
        timeout = httpx.Timeout(connect=15.0, read=300.0, write=60.0, pool=60.0)
        _shared_client = httpx.AsyncClient(limits=limits, timeout=timeout)
    return _shared_client

async def close_shared_client():
    global _shared_client
    if _shared_client and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None

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

async def probe_model(api_key: str, client: httpx.AsyncClient, model_id: str, sem: asyncio.Semaphore, base_url: str = NIM_API_BASE, timeout_sec: float = 8.0) -> tuple[bool, float]:
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
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 5,
                    "temperature": 0.0
                },
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

async def discover_models(api_keys: list[str] | str, latencies_dict: dict, openrouter_key: str = "", opencode_key: str = "", groq_keys: list[str] | str = "", cerebras_keys: list[str] | str = "", bai_key: str = "") -> list[dict]:
    primary_nvidia_key = api_keys[0] if isinstance(api_keys, list) and api_keys else (api_keys if isinstance(api_keys, str) else "")
    primary_groq_key = groq_keys[0] if isinstance(groq_keys, list) and groq_keys else (groq_keys if isinstance(groq_keys, str) else "")
    primary_cerebras_key = cerebras_keys[0] if isinstance(cerebras_keys, list) and cerebras_keys else (cerebras_keys if isinstance(cerebras_keys, str) else "")

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

    if openrouter_key:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{OPENROUTER_API_BASE}/models",
                    headers={"Authorization": f"Bearer {openrouter_key}"},
                )
                if response.status_code == 200:
                    data = response.json()
                    or_models = [m for m in data.get("data", []) if m.get("id", "").endswith(":free")]
                    for m in or_models:
                        m_copy = dict(m)
                        m_copy["provider"] = "OpenRouter"
                        candidates_to_probe.append((openrouter_key, m_copy, OPENROUTER_API_BASE))
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

    if not all_discovered:
        all_discovered = load_fallback_models(latencies_dict)
        for m in all_discovered:
            if "provider" not in m:
                m["provider"] = "NVIDIA"

    all_discovered.sort(key=lambda m: latencies_dict.get(m.get("id", ""), 999.0))
    logger.success(f"Multi-provider model discovery complete: {len(all_discovered)} active models in pool.")
    return all_discovered

async def call_provider_endpoint(api_key: str, model_id: str, request: ChatCompletionRequest, base_url: str = NIM_API_BASE) -> Response:
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

    client = get_shared_client()

    if request.stream:
        try:
            req = client.build_request("POST", url, headers=headers, json=payload)
            response = await client.send(req, stream=True)

            if response.status_code == 200:
                aiter = response.aiter_raw()
                first_chunk = None
                try:
                    first_chunk = await aiter.__anext__()
                except StopAsyncIteration:
                    first_chunk = None

                if first_chunk:
                    sample = first_chunk.decode("utf-8", errors="ignore")
                    if '"error":' in sample and ('"message":' in sample or '"code":' in sample):
                        await response.aclose()
                        await client.aclose()
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

                async def stream_generator():
                    try:
                        if first_chunk:
                            yield first_chunk
                        async for chunk in aiter:
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
                retry_sec = parse_retry_after(response.headers.get("Retry-After") or response.headers.get("retry-after"))
                await response.aclose()
                await client.aclose()
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
    else:
        try:
            response = await client.post(url, headers=headers, json=payload)
            retry_sec = parse_retry_after(response.headers.get("Retry-After") or response.headers.get("retry-after"))

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
