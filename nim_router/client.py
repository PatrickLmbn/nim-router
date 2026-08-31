import asyncio
import json
import sys
import time
import httpx
from fastapi import HTTPException, Response
from fastapi.responses import StreamingResponse

from nim_router.config import NIM_API_BASE
from nim_router.logger import logger
from nim_router.schemas import ChatCompletionRequest
from nim_router.catalog import is_banned_model, load_fallback_models

async def probe_model(api_key: str, client: httpx.AsyncClient, model_id: str, sem: asyncio.Semaphore) -> tuple[bool, float]:
    if is_banned_model(model_id):
        return False, 999.0
    async with sem:
        t0 = time.time()
        try:
            resp = await client.post(
                f"{NIM_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
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

async def discover_models(api_key: str, latencies_dict: dict) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{NIM_API_BASE}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if response.status_code != 200:
                logger.warning(f"Model discovery returned {response.status_code}")
                return load_fallback_models(latencies_dict)

            data = response.json()
            all_models = data.get("data", [])
            logger.info(f"Discovered {len(all_models)} total models from NVIDIA API. Filtering non-chat/banned models...")

            sem = asyncio.Semaphore(10)
            valid_models = [
                m for m in all_models
                if m.get("id") and not is_banned_model(m.get("id"))
            ]
            total_probes = len(valid_models)
            completed_count = 0
            lock = asyncio.Lock()

            async def probe_with_progress(m_obj):
                nonlocal completed_count
                mid = m_obj.get("id", "")
                ok, latency = await probe_model(api_key, client, mid, sem)
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
                    latencies_dict[mid] = latency
                    accessible_models.append(m)

            accessible_models.sort(key=lambda m: latencies_dict.get(m.get("id", ""), 999.0))

            logger.success(
                f"Probe complete: {len(accessible_models)} working chat models found (filtered out non-working & banned models)"
            )
            top_3 = accessible_models[:3]
            logger.info("Top-3 Priority Models (Lowest Latency):")
            for rank, m in enumerate(top_3, 1):
                mid = m.get("id", "")
                logger.info(f"  {rank}. {mid} ({latencies_dict.get(mid, 0.0):.3f}s)")

            for m in accessible_models[3:]:
                mid = m.get("id", "")
                logger.info(f"  - Standby Model: {mid} ({latencies_dict.get(mid, 0.0):.3f}s)")

            return accessible_models

    except Exception as e:
        logger.error(f"Model discovery failed: {e}, falling back to verified working list")
        return load_fallback_models(latencies_dict)

async def call_nvidia_endpoint(api_key: str, model_id: str, request: ChatCompletionRequest) -> Response:
    url = f"{NIM_API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
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

    timeout_config = httpx.Timeout(connect=15.0, read=300.0, write=60.0, pool=60.0)
    client = httpx.AsyncClient(timeout=timeout_config)

    if request.stream:
        try:
            req = client.build_request("POST", url, headers=headers, json=payload)
            response = await client.send(req, stream=True)

            if response.status_code == 200:
                async def stream_generator():
                    try:
                        async for chunk in response.aiter_raw():
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
