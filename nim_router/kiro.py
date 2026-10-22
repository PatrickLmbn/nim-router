
import asyncio
import base64
import binascii
import json
import os
import sqlite3
import time
import uuid
from typing import Any, AsyncIterator, Optional

import httpx

from nim_router.logger import logger


KIRO_API_BASE = "https://q.us-east-1.amazonaws.com/"
KIRO_AUTH_URL = "https://prod.us-east-1.auth.desktop.kiro.dev/refreshToken"
KIRO_USER_AGENT = "kiro-cli/2.19.2 (external-01; cli-desktop)"

KIRO_GENERATE_TARGET = "AmazonCodeWhispererStreamingService.GenerateAssistantResponse"
KIRO_LIST_MODELS_TARGET = "AmazonCodeWhispererService.ListAvailableModels"

KIRO_ORIGIN = "AI_EDITOR"
KIRO_PREFIX = "kiro/"

_TOKEN_EXPIRY_MARGIN = 120.0

_DEFAULT_LATENCY = 2.0


def kiro_upstream_model_id(model_id: str) -> str:
    mid = (model_id or "").strip()
    if mid.startswith("[Kiro] "):
        mid = mid[len("[Kiro] "):].strip()
    if mid.lower().startswith(KIRO_PREFIX):
        mid = mid[len(KIRO_PREFIX):].strip()
    return mid


def _extract_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") in ("text", "input_text") or "text" in item:
                    parts.append(str(item.get("text", "")))
        return "".join(parts)
    if isinstance(content, dict):
        return str(content.get("text", "") or "")
    return str(content)


def _data_uri_to_image(url: str) -> Optional[dict]:
    if not url.startswith("data:"):
        return None
    try:
        header, b64 = url.split(",", 1)
    except ValueError:
        return None
    if ";base64" not in header:
        return None
    mime = header[5:].split(";")[0].strip().lower() or "image/png"
    fmt = mime.split("/")[-1] or "png"
    if fmt == "jpeg":
        fmt = "jpg"
    try:
        base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        return None
    return {"format": fmt, "source": {"bytes": b64}}


async def _http_url_to_image(url: str, client: httpx.AsyncClient) -> Optional[dict]:
    try:
        resp = await client.get(url, timeout=20.0)
        if resp.status_code != 200:
            return None
        content_type = resp.headers.get("content-type", "image/png").split(";")[0].strip().lower()
        fmt = content_type.split("/")[-1] or "png"
        if fmt == "jpeg":
            fmt = "jpg"
        b64 = base64.b64encode(resp.content).decode("ascii")
        return {"format": fmt, "source": {"bytes": b64}}
    except Exception:
        return None


def _parse_headers(region: bytes) -> dict:
    headers: dict = {}
    j = 0
    n = len(region)
    while j < n:
        name_len = region[j]
        j += 1
        if j + name_len > n:
            break
        name = region[j:j + name_len].decode("utf-8", "replace")
        j += name_len
        if j >= n:
            break
        value_type = region[j]
        j += 1
        if value_type == 7:
            if j + 2 > n:
                break
            value_len = int.from_bytes(region[j:j + 2], "big")
            j += 2
            value = region[j:j + value_len].decode("utf-8", "replace")
            j += value_len
        elif value_type == 0:
            value = True
        elif value_type == 1:
            value = False
        elif value_type == 2:
            value = int.from_bytes(region[j:j + 1], "big", signed=True)
            j += 1
        elif value_type == 3:
            value = int.from_bytes(region[j:j + 2], "big", signed=True)
            j += 2
        elif value_type == 4:
            value = int.from_bytes(region[j:j + 4], "big", signed=True)
            j += 4
        elif value_type in (5, 8):
            import struct
            value = struct.unpack(">d", region[j:j + 8])[0]
            j += 8
        elif value_type == 6:
            value = region[j:j + 8]
            j += 8
        elif value_type == 9:
            value = region[j:j + 16]
            j += 16
        else:
            value = None
        headers[name] = value
    return headers


def _decode_json_object(payload: bytes) -> Any:
    start = payload.find(b"{")
    if start < 0:
        return None
    try:
        text = payload[start:].decode("utf-8", "replace")
        obj, _ = json.JSONDecoder().raw_decode(text)
        return obj
    except Exception:
        return None


class _FrameDecoder:

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> list[tuple[str, Any]]:
        self._buf.extend(chunk)
        events: list[tuple[str, Any]] = []
        while True:
            if len(self._buf) < 12:
                break
            total = int.from_bytes(self._buf[0:4], "big")
            header_len = int.from_bytes(self._buf[4:8], "big")
            if total < 16 or total > 16 * 1024 * 1024:
                self._buf.clear()
                break
            if len(self._buf) < total:
                break
            frame = bytes(self._buf[:total])
            del self._buf[:total]
            event = self._parse_frame(frame, header_len)
            if event is not None:
                events.append(event)
        return events

    @staticmethod
    def _parse_frame(frame: bytes, header_len: int) -> Optional[tuple[str, Any]]:
        total = len(frame)
        headers = _parse_headers(frame[12:12 + header_len])
        payload = frame[12 + header_len:total - 4]
        event_type = str(headers.get(":event-type", "") or "")
        return event_type, _decode_json_object(payload)


def resolve_refresh_token(explicit: str = "") -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    try:
        from nim_router.kiro_login import load_stored_refresh_token
        return load_stored_refresh_token()
    except Exception:
        return ""


class KiroAuth:

    def __init__(self, refresh_token: str = "") -> None:
        self.refresh_token = (refresh_token or "").strip()
        self.access_token = ""
        self.profile_arn = ""
        self.expires_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.refresh_token)

    async def ensure_token(self) -> tuple[str, str]:
        if not self.refresh_token:
            raise RuntimeError("Kiro is not configured: no refresh token available.")
        async with self._lock:
            now = time.time()
            if self.access_token and now < self.expires_at - _TOKEN_EXPIRY_MARGIN:
                return self.access_token, self.profile_arn
            await self._refresh()
            return self.access_token, self.profile_arn

    async def _refresh(self) -> None:
        payload = {"refreshToken": self.refresh_token}
        headers = {
            "Content-Type": "application/json",
            "User-Agent": KIRO_USER_AGENT,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(KIRO_AUTH_URL, json=payload, headers=headers)
        except Exception as e:
            raise RuntimeError(f"Kiro token refresh failed: {e}") from e

        if resp.status_code != 200:
            raise RuntimeError(
                f"Kiro token refresh failed with HTTP {resp.status_code}: {resp.text[:200]}"
            )
        try:
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Kiro token refresh returned invalid JSON: {e}") from e

        access_token = data.get("accessToken") or ""
        profile_arn = data.get("profileArn") or self.profile_arn
        if not access_token:
            raise RuntimeError("Kiro token refresh response did not contain an accessToken.")

        rotated = data.get("refreshToken") or ""
        if rotated and rotated != self.refresh_token:
            self.refresh_token = rotated

        self.access_token = access_token
        self.profile_arn = profile_arn
        try:
            ttl = float(data.get("expiresIn") or 3600)
        except (TypeError, ValueError):
            ttl = 3600.0
        self.expires_at = time.time() + ttl
        logger.info("Kiro access token refreshed (valid for %ds).", int(ttl))


def _convert_tools(tools: Optional[list[dict]]) -> list[dict]:
    converted: list[dict] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") or tool
        name = fn.get("name")
        if not name:
            continue
        parameters = fn.get("parameters") or fn.get("inputSchema") or {}
        if not isinstance(parameters, dict) or not parameters:
            parameters = {"type": "object", "properties": {}}
        converted.append({
            "toolSpecification": {
                "name": name,
                "description": fn.get("description") or "",
                "inputSchema": {"json": parameters},
            }
        })
    return converted


def _tool_uses_from_message(msg: dict) -> list[dict]:
    uses: list[dict] = []
    for call in msg.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        fn = call.get("function") or {}
        raw_args = fn.get("arguments")
        if isinstance(raw_args, dict):
            parsed = raw_args
        else:
            try:
                parsed = json.loads(raw_args or "{}")
            except (TypeError, ValueError):
                parsed = {}
        uses.append({
            "name": fn.get("name", ""),
            "input": parsed if isinstance(parsed, dict) else {},
            "toolUseId": call.get("id", ""),
        })
    return uses


def _tool_results_from_message(msg: dict) -> list[dict]:
    text = _extract_text(msg.get("content"))
    return [{
        "content": [{"text": text if text else "(empty result)"}],
        "status": "success",
        "toolUseId": msg.get("tool_call_id") or "",
    }]


def _collect_images(content: Any) -> list[dict]:
    found: list[dict] = []
    if not isinstance(content, list):
        return found
    for item in content:
        if not isinstance(item, dict):
            continue
        url = None
        if item.get("type") in ("image_url", "image", "input_image"):
            image_url = item.get("image_url")
            if isinstance(image_url, dict):
                url = image_url.get("url")
            elif isinstance(image_url, str):
                url = image_url
        elif item.get("image_url"):
            image_url = item["image_url"]
            url = image_url.get("url") if isinstance(image_url, dict) else image_url
        if url:
            found.append({"url": url})
    return found


async def _resolve_images(images: list[dict], client: httpx.AsyncClient) -> list[dict]:
    resolved: list[dict] = []
    for image in images:
        url = image.get("url") or ""
        block = _data_uri_to_image(url)
        if block is None and url.startswith(("http://", "https://")):
            block = await _http_url_to_image(url, client)
        if block is not None:
            resolved.append(block)
        else:
            logger.warning("Kiro: could not resolve image reference; skipping it.")
    return resolved


async def build_kiro_payload(
    messages: list[dict],
    model_id: str,
    tools: Optional[list[dict]] = None,
    profile_arn: str = "",
    client: Optional[httpx.AsyncClient] = None,
) -> dict:
    system_chunks: list[str] = []
    turns: list[dict] = []
    pending_results: list[dict] = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "user")
        if role == "system":
            text = _extract_text(msg.get("content"))
            if text.strip():
                system_chunks.append(text.strip())
            continue
        if role == "tool":
            pending_results.extend(_tool_results_from_message(msg))
            continue
        if role == "assistant":
            if pending_results:
                turns.append({"kind": "user", "content": "", "images": [], "tool_results": pending_results})
                pending_results = []
            turns.append({
                "kind": "assistant",
                "content": _extract_text(msg.get("content")),
                "tool_uses": _tool_uses_from_message(msg),
            })
            continue
        if pending_results:
            turns.append({"kind": "user", "content": "", "images": [], "tool_results": pending_results})
            pending_results = []
        turns.append({
            "kind": "user",
            "content": _extract_text(msg.get("content")),
            "images": _collect_images(msg.get("content")),
            "tool_results": [],
        })

    if pending_results:
        turns.append({"kind": "user", "content": "", "images": [], "tool_results": pending_results})

    merged: list[dict] = []
    for turn in turns:
        if merged and merged[-1]["kind"] == turn["kind"]:
            prev = merged[-1]
            if turn["kind"] == "user":
                if turn["content"]:
                    prev["content"] = f"{prev['content']}\n{turn['content']}".strip() if prev["content"] else turn["content"]
                prev["images"].extend(turn["images"])
                prev["tool_results"].extend(turn["tool_results"])
            else:
                if turn["content"]:
                    prev["content"] = f"{prev['content']}\n{turn['content']}".strip() if prev["content"] else turn["content"]
                prev["tool_uses"].extend(turn["tool_uses"])
        else:
            merged.append(dict(turn))

    if not merged:
        merged = [{"kind": "user", "content": "Continue", "images": [], "tool_results": []}]

    if merged[-1]["kind"] == "assistant":
        merged.append({"kind": "user", "content": "Continue", "images": [], "tool_results": []})

    if system_chunks:
        system_prompt = "\n\n".join(system_chunks)
        for turn in merged:
            if turn["kind"] == "user":
                turn["content"] = f"{system_prompt}\n\n{turn['content']}".strip()
                break

    own_client = client is None
    http_client = client or httpx.AsyncClient(timeout=30.0)
    try:
        for turn in merged:
            if turn["kind"] == "user" and turn["images"]:
                turn["images"] = await _resolve_images(turn["images"], http_client)
    finally:
        if own_client:
            await http_client.aclose()

    kiro_tools = _convert_tools(tools)

    def _user_turn(turn: dict) -> dict:
        context: dict = {}
        if kiro_tools:
            context["tools"] = kiro_tools
        if turn["tool_results"]:
            context["toolResults"] = turn["tool_results"]
        return {
            "userInputMessage": {
                "content": turn["content"] or "Continue",
                "modelId": model_id,
                "origin": KIRO_ORIGIN,
                "images": turn["images"],
                "userInputMessageContext": context,
            }
        }

    def _assistant_turn(turn: dict) -> dict:
        message: dict = {"content": turn["content"] or ""}
        if turn["tool_uses"]:
            message["toolUses"] = turn["tool_uses"]
        return {"assistantResponseMessage": message}

    history: list[dict] = []
    for turn in merged[:-1]:
        history.append(_user_turn(turn) if turn["kind"] == "user" else _assistant_turn(turn))
    current = _user_turn(merged[-1])

    payload: dict = {
        "conversationState": {
            "chatTriggerType": "MANUAL",
            "conversationId": None,
            "currentMessage": current,
            "history": history,
        },
        "modelId": model_id,
    }
    if profile_arn:
        payload["profileArn"] = profile_arn
    return payload


class _ToolCallAccumulator:

    def __init__(self) -> None:
        self._calls: dict[str, dict] = {}
        self._order: list[str] = []

    def add(self, body: dict) -> None:
        tool_use_id = body.get("toolUseId") or ""
        if not tool_use_id:
            return
        if tool_use_id not in self._calls:
            self._calls[tool_use_id] = {"name": "", "input": "", "index": len(self._order)}
            self._order.append(tool_use_id)
        call = self._calls[tool_use_id]
        if body.get("name"):
            call["name"] = body["name"]
        if isinstance(body.get("input"), str) and body["input"]:
            call["input"] += body["input"]

    def complete(self) -> list[dict]:
        results = []
        for tool_use_id in self._order:
            call = self._calls[tool_use_id]
            raw = call["input"] or "{}"
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError):
                parsed = {}
            results.append({
                "id": tool_use_id,
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(parsed) if isinstance(parsed, dict) else raw,
                },
            })
        return results


def _chunk_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")


class KiroClient:

    def __init__(self, auth: KiroAuth) -> None:
        self.auth = auth

    def _headers(self, access_token: str, target: str) -> dict:
        return {
            "Content-Type": "application/x-amz-json-1.0",
            "X-Amz-Target": target,
            "Authorization": f"Bearer {access_token}",
            "User-Agent": KIRO_USER_AGENT,
        }

    async def list_models(self) -> list[dict]:
        access_token, profile_arn = await self.auth.ensure_token()
        body: dict = {"origin": KIRO_ORIGIN}
        if profile_arn:
            body["profileArn"] = profile_arn
        headers = self._headers(access_token, KIRO_LIST_MODELS_TARGET)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(KIRO_API_BASE, json=body, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Kiro model list failed with HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        models = data.get("models") or []
        catalogue: list[dict] = []
        for model in models:
            if not isinstance(model, dict):
                continue
            model_id = model.get("modelId") or model.get("modelName")
            if not model_id:
                continue
            limits = model.get("tokenLimits") or {}
            catalogue.append({
                "id": f"{KIRO_PREFIX}{model_id}",
                "provider": "Kiro",
                "kiro_model_id": model_id,
                "description": model.get("description", ""),
                "rate_multiplier": model.get("rateMultiplier"),
                "rate_unit": model.get("rateUnit", ""),
                "supports_image": "IMAGE" in (model.get("supportedInputTypes") or []),
                "max_input_tokens": limits.get("maxInputTokens"),
                "max_output_tokens": limits.get("maxOutputTokens"),
            })
        return catalogue

    async def stream_events(
        self,
        payload: dict,
        client: httpx.AsyncClient,
    ) -> AsyncIterator[tuple[str, Any]]:
        access_token, _ = await self.auth.ensure_token()
        headers = self._headers(access_token, KIRO_GENERATE_TARGET)
        req = client.build_request("POST", KIRO_API_BASE, headers=headers, json=payload)
        response = await client.send(req, stream=True)
        if response.status_code != 200:
            body = await response.aread()
            detail = body.decode("utf-8", "replace")[:400]
            await response.aclose()
            raise RuntimeError(f"Kiro request failed with HTTP {response.status_code}: {detail}")

        decoder = _FrameDecoder()
        try:
            async for chunk in response.aiter_bytes():
                for event_type, body in decoder.feed(chunk):
                    yield event_type, body
        finally:
            await response.aclose()


    async def create_chat_completion(
        self,
        model_id: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        client: Optional[httpx.AsyncClient] = None,
    ) -> dict:
        upstream_id = kiro_upstream_model_id(model_id)
        _access_token, profile_arn = await self.auth.ensure_token()
        own_client = client is None
        http_client = client or httpx.AsyncClient(timeout=300.0)
        try:
            payload = await build_kiro_payload(
                messages, upstream_id, tools=tools, profile_arn=profile_arn, client=http_client
            )
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            tool_calls = _ToolCallAccumulator()
            credits = 0.0

            async for event_type, body in self.stream_events(payload, http_client):
                if not isinstance(body, dict):
                    continue
                if event_type == "assistantResponseEvent":
                    text = body.get("content")
                    if isinstance(text, str) and text:
                        content_parts.append(text)
                elif event_type == "reasoningContentEvent":
                    text = body.get("text")
                    if isinstance(text, str) and text:
                        reasoning_parts.append(text)
                elif event_type == "toolUseEvent":
                    tool_calls.add(body)
                elif event_type == "meteringEvent":
                    try:
                        credits = float(body.get("usage") or 0.0)
                    except (TypeError, ValueError):
                        credits = 0.0
        finally:
            if own_client:
                await http_client.aclose()

        content = "".join(content_parts)
        reasoning = "".join(reasoning_parts)
        message: dict = {"role": "assistant", "content": content or None}
        if reasoning:
            message["reasoning_content"] = reasoning
        calls = tool_calls.complete()
        if calls:
            message["tool_calls"] = calls
        if message.get("content") is None and not calls:
            message["content"] = ""

        prompt_tokens = estimate_tokens(messages)
        completion_tokens = max(1, int(len(content) / 3.8)) if content else 0
        if calls:
            completion_tokens = max(completion_tokens, sum(len(c["function"]["arguments"]) for c in calls) // 3)

        return {
            "id": _chunk_id(),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_id,
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if calls else "stop",
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "kiro": {"credits": credits},
        }

    async def stream_chat_completion(
        self,
        model_id: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> AsyncIterator[bytes]:
        upstream_id = kiro_upstream_model_id(model_id)
        _access_token, profile_arn = await self.auth.ensure_token()

        own_client = client is None
        http_client = client or httpx.AsyncClient(timeout=300.0)
        completion_id = _chunk_id()
        created = int(time.time())

        def base_chunk(delta: dict, finish_reason: Optional[str] = None) -> dict:
            return {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_id,
                "choices": [{
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }],
            }

        try:
            payload = await build_kiro_payload(
                messages, upstream_id, tools=tools, profile_arn=profile_arn, client=http_client
            )
            tool_calls = _ToolCallAccumulator()
            content_parts: list[str] = []

            yield _sse(base_chunk({"role": "assistant", "content": ""}))

            async for event_type, body in self.stream_events(payload, http_client):
                if not isinstance(body, dict):
                    continue
                if event_type == "assistantResponseEvent":
                    text = body.get("content")
                    if isinstance(text, str) and text:
                        content_parts.append(text)
                        yield _sse(base_chunk({"content": text}))
                elif event_type == "reasoningContentEvent":
                    text = body.get("text")
                    if isinstance(text, str) and text:
                        yield _sse(base_chunk({"reasoning_content": text}))
                elif event_type == "toolUseEvent":
                    tool_calls.add(body)

            calls = tool_calls.complete()
            if calls:
                for call in calls:
                    yield _sse(base_chunk({
                        "tool_calls": [{
                            "index": 0,
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["function"]["name"],
                                "arguments": call["function"]["arguments"],
                            },
                        }]
                    }))
                yield _sse(base_chunk({}, finish_reason="tool_calls"))
            else:
                yield _sse(base_chunk({}, finish_reason="stop"))

            prompt_tokens = estimate_tokens(messages)
            completion_tokens = max(1, int(len("".join(content_parts)) / 3.8)) if content_parts else 0
            yield _sse({
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_id,
                "choices": [],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            })
            yield b"data: [DONE]\n\n"
        finally:
            if own_client:
                await http_client.aclose()


def estimate_tokens(messages: list[dict]) -> int:
    total_words = 0
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        text = _extract_text(msg.get("content"))
        total_words += len(text.split())
    return int(total_words / 0.75)
