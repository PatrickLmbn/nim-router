
import asyncio
import base64
import binascii
import json
import re
import os
import time
import uuid
from typing import Any, AsyncGenerator, AsyncIterator, Optional

import httpx

from nim_router.logger import logger


ANTIGRAVITY_API_BASE = "https://daily-cloudcode-pa.googleapis.com"
ANTIGRAVITY_PROD_API_BASE = "https://cloudcode-pa.googleapis.com"
ANTIGRAVITY_API_VERSION = "v1internal"

from nim_router.antigravity_oauth import get_client_id as _get_client_id, get_client_secret as _get_client_secret
ANTIGRAVITY_TOKEN_URL = "https://oauth2.googleapis.com/token"
ANTIGRAVITY_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo?alt=json"

ANTIGRAVITY_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
    "https://www.googleapis.com/auth/aicode",
)

ANTIGRAVITY_REQUIRED_SCOPES = (
    "https://www.googleapis.com/auth/aicode",
)

ANTIGRAVITY_DEFAULT_PROJECT = "aicode-consumers"
ANTIGRAVITY_USER_AGENT = "antigravity/cli/1.4.4 (aidev_client; os_type=linux; arch=amd64; cl=1003595037; auth_method=consumer)"
ANTIGRAVITY_PREFIX = "antigravity/"

_TOKEN_EXPIRY_MARGIN = 120.0

_DEFAULT_LATENCY = 2.0

_MODEL_FALLBACKS = [
    {
        "id": "gemini-3.8-flash-high",
        "provider": "Antigravity",
        "antigravity_model_id": "gemini-3.8-flash-high",
        "description": "Gemini 3.8 Flash (High effort)",
        "supports_image": True,
    },
    {
        "id": "claude-sonnet-4-6",
        "provider": "Antigravity",
        "antigravity_model_id": "claude-sonnet-4-6",
        "description": "Claude Sonnet 4.6",
        "supports_image": True,
    },
    {
        "id": "claude-opus-4-6-thinking",
        "provider": "Antigravity",
        "antigravity_model_id": "claude-opus-4-6-thinking",
        "description": "Claude Opus 4.6 (Thinking)",
        "supports_image": True,
    },
]


def antigravity_upstream_model_id(model_id: str) -> str:
    mid = (model_id or "").strip()
    if mid.startswith("[Antigravity] "):
        mid = mid[len("[Antigravity] "):].strip()
    if mid.lower().startswith(ANTIGRAVITY_PREFIX):
        mid = mid[len(ANTIGRAVITY_PREFIX):].strip()
    return mid


def antigravity_api_base() -> str:
    return os.getenv("ANTIGRAVITY_API_BASE", "").strip() or ANTIGRAVITY_API_BASE


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
    return {"mimeType": mime or "image/png", "data": b64}


async def _http_url_to_image(url: str, client: httpx.AsyncClient) -> Optional[dict]:
    try:
        resp = await client.get(url, timeout=20.0)
        if resp.status_code != 200:
            return None
        content_type = resp.headers.get("content-type", "image/png").split(";")[0].strip().lower()
        mime = content_type or "image/png"
        b64 = base64.b64encode(resp.content).decode("ascii")
        return {"mimeType": mime, "data": b64}
    except Exception:
        return None


_JSON_SCHEMA_ALLOWED_FIELDS = frozenset({
    "type", "properties", "items", "required", "description", "title",
    "minimum", "maximum",
    "minLength", "maxLength", "pattern", "format",
    "minItems", "maxItems",
    "minProperties", "maxProperties", "additionalProperties",
    "enum", "default",
    "anyOf", "oneOf", "allOf", "not",
    "nullable", "example",
})


def _sanitize_schema(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema

    cleaned: dict = {}
    for key, value in schema.items():
        if key not in _JSON_SCHEMA_ALLOWED_FIELDS:
            continue
        if key == "properties":
            if isinstance(value, dict):
                cleaned[key] = {pname: _sanitize_schema(pschema) for pname, pschema in value.items()}
            else:
                cleaned[key] = value
        elif isinstance(value, dict):
            cleaned[key] = _sanitize_schema(value)
        elif isinstance(value, list):
            cleaned[key] = [_sanitize_schema(item) for item in value]
        else:
            cleaned[key] = value

    return cleaned


def _normalize_schema(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema

    stype = schema.get("type")
    if stype == "array" and "items" not in schema:
        schema["items"] = {"type": "string"}
    elif "properties" in schema and stype is None:
        schema["type"] = "object"
    elif "properties" in schema and stype != "object":
        schema.pop("properties", None)

    if isinstance(schema.get("properties"), dict):
        schema["properties"] = {
            pname: _normalize_schema(pschema) for pname, pschema in schema["properties"].items()
        }
    if isinstance(schema.get("items"), dict):
        schema["items"] = _normalize_schema(schema["items"])
    if isinstance(schema.get("additionalProperties"), dict):
        schema["additionalProperties"] = _normalize_schema(schema["additionalProperties"])
    for key in ("anyOf", "oneOf", "allOf"):
        if isinstance(schema.get(key), list):
            schema[key] = [_normalize_schema(item) for item in schema[key]]
    if isinstance(schema.get("not"), dict):
        schema["not"] = _normalize_schema(schema["not"])

    return schema


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
        parameters = _normalize_schema(_sanitize_schema(parameters))
        declarations = [{
            "name": name,
            "description": fn.get("description") or "",
            "parameters": parameters,
        }]
        converted.append({"functionDeclarations": declarations})
    return converted


_THOUGHT_SIGNATURES: dict[str, str] = {}
_THOUGHT_SIGNATURES_MAX = 4096


def _remember_thought_signature(call_id: str, signature: str) -> None:
    if not call_id or not signature:
        return
    if len(_THOUGHT_SIGNATURES) >= _THOUGHT_SIGNATURES_MAX:
        for stale in list(_THOUGHT_SIGNATURES)[: _THOUGHT_SIGNATURES_MAX // 4]:
            _THOUGHT_SIGNATURES.pop(stale, None)
    _THOUGHT_SIGNATURES[call_id] = signature


def _thought_signature_for(call: dict) -> str:
    extra = call.get("extra_content")
    if isinstance(extra, dict):
        google = extra.get("google")
        if isinstance(google, dict):
            signature = google.get("thought_signature")
            if isinstance(signature, str) and signature:
                return signature
        signature = extra.get("thought_signature")
        if isinstance(signature, str) and signature:
            return signature
    for key in ("thoughtSignature", "thought_signature"):
        signature = call.get(key)
        if isinstance(signature, str) and signature:
            return signature
    signature = _THOUGHT_SIGNATURES.get(str(call.get("id") or ""))
    if signature:
        return signature
    fn = call.get("function") or {}
    raw_args = fn.get("arguments")
    if not isinstance(raw_args, str):
        raw_args = json.dumps(raw_args) if isinstance(raw_args, dict) else ""
    return _THOUGHT_SIGNATURES.get(f"{fn.get('name') or ''}|{raw_args}", "")


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
        func_call = {
            "id": call.get("id", ""),
            "name": fn.get("name", ""),
            "args": parsed if isinstance(parsed, dict) else {},
        }
        part: dict = {"functionCall": func_call}
        signature = _thought_signature_for(call)
        if signature:
            part["thoughtSignature"] = signature
        uses.append(part)
    return uses


def _tool_results_from_message(msg: dict, tool_call_map: Optional[dict[str, str]] = None) -> list[dict]:
    text = _extract_text(msg.get("content"))
    tool_call_id = msg.get("tool_call_id") or ""
    name = msg.get("name") or (tool_call_map.get(tool_call_id) if tool_call_map else "") or ""
    return [{
        "functionResponse": {
            "id": tool_call_id,
            "name": name,
            "response": {"output": text if text else "(empty result)"},
        }
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
            logger.warning("Antigravity: could not resolve image reference; skipping it.")
    return resolved


def resolve_refresh_token(explicit: str = "") -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    try:
        from nim_router.antigravity_login import load_stored_refresh_token
        return load_stored_refresh_token()
    except Exception:
        return ""


class AntigravityAuth:

    def __init__(self, refresh_token: str = "") -> None:
        self.refresh_token = (refresh_token or "").strip()
        self.access_token = ""
        self.email = ""
        self.project_id = ""
        self.expires_at = 0.0
        self.scopes_ok = True
        self.missing_scopes: list[str] = []
        self._lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.refresh_token)

    async def ensure_token(self) -> str:
        if not self.refresh_token:
            raise RuntimeError("Antigravity is not configured: no refresh token available.")
        async with self._lock:
            now = time.time()
            if self.access_token and now < self.expires_at - _TOKEN_EXPIRY_MARGIN:
                return self.access_token
            await self._refresh()
            return self.access_token

    async def _refresh(self) -> None:
        payload = {
            "client_id": _get_client_id(),
            "client_secret": _get_client_secret(),
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(ANTIGRAVITY_TOKEN_URL, data=payload, headers=headers)
        except Exception as e:
            raise RuntimeError(f"Antigravity token refresh failed: {e}") from e

        if resp.status_code != 200:
            raise RuntimeError(
                f"Antigravity token refresh failed with HTTP {resp.status_code}: {resp.text[:200]}"
            )
        try:
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Antigravity token refresh returned invalid JSON: {e}") from e

        access_token = data.get("access_token") or ""
        if not access_token:
            raise RuntimeError("Antigravity token refresh response did not contain an access_token.")

        rotated = data.get("refresh_token") or ""
        if rotated and rotated != self.refresh_token:
            self.refresh_token = rotated

        self.access_token = access_token
        try:
            ttl = float(data.get("expires_in") or 3600)
        except (TypeError, ValueError):
            ttl = 3600.0
        self.expires_at = time.time() + ttl
        await self._verify_scopes()
        logger.info("Antigravity access token refreshed (valid for %ds).", int(ttl))

    async def _verify_scopes(self) -> None:
        if not self.access_token:
            return
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    "https://oauth2.googleapis.com/tokeninfo",
                    params={"access_token": self.access_token},
                )
            if resp.status_code != 200:
                return
            granted = set((resp.json().get("scope") or "").split())
        except Exception:
            return
        missing = [s for s in ANTIGRAVITY_REQUIRED_SCOPES if s not in granted]
        if missing:
            self.scopes_ok = False
            self.missing_scopes = missing
            logger.warning(
                "Antigravity token is missing required scope(s): %s. Sign in again to grant them.",
                ", ".join(missing),
            )
        else:
            self.scopes_ok = True
            self.missing_scopes = []

    async def fetch_user_info(self) -> dict:
        token = await self.ensure_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": ANTIGRAVITY_USER_AGENT,
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(ANTIGRAVITY_USERINFO_URL, headers=headers)
        except Exception:
            return {}
        if resp.status_code != 200:
            return {}
        try:
            data = resp.json()
        except Exception:
            return {}
        if isinstance(data, dict):
            return data
        return {}


async def build_antigravity_payload(
    messages: list[dict],
    model_id: str,
    tools: Optional[list[dict]] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> dict:
    system_chunks: list[str] = []
    contents: list[dict] = []
    pending_results: list[dict] = []
    tool_call_map: dict[str, str] = {}

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
            pending_results.extend(_tool_results_from_message(msg, tool_call_map))
            continue
        if role == "assistant":
            for call in msg.get("tool_calls") or []:
                if isinstance(call, dict):
                    fn = call.get("function") or {}
                    call_id = call.get("id")
                    name = fn.get("name")
                    if call_id and name:
                        tool_call_map[call_id] = name
            if pending_results:
                contents.append({"role": "user", "parts": pending_results})
                pending_results = []
            parts: list[dict] = []
            text = _extract_text(msg.get("content"))
            if text:
                parts.append({"text": text})
            parts.extend(_tool_uses_from_message(msg))
            contents.append({"role": "model", "parts": parts})
            continue
        if pending_results:
            contents.append({"role": "user", "parts": pending_results})
            pending_results = []
        parts = []
        text = _extract_text(msg.get("content"))
        if text:
            parts.append({"text": text})
        images = _collect_images(msg.get("content"))
        for image in images:
            parts.append({"inlineData": {"mimeType": "image/png", "data": ""}})
        contents.append({"role": "user", "parts": parts, "_images": images})

    if pending_results:
        contents.append({"role": "user", "parts": pending_results})

    if not contents:
        contents = [{"role": "user", "parts": [{"text": "Continue"}]}]

    own_client = client is None
    http_client = client or httpx.AsyncClient(timeout=30.0)
    try:
        for entry in contents:
            images = entry.pop("_images", None)
            if not images:
                continue
            resolved = await _resolve_images(images, http_client)
            if not resolved:
                entry["parts"] = [p for p in entry["parts"] if "inlineData" not in p]
                continue
            entry["parts"] = [p for p in entry["parts"] if "inlineData" not in p]
            for image in resolved:
                entry["parts"].append({"inlineData": image})
    finally:
        if own_client:
            await http_client.aclose()

    request: dict = {"contents": contents}

    if system_chunks:
        request["systemInstruction"] = {
            "role": "user",
            "parts": [{"text": "\n\n".join(system_chunks)}],
        }

    ag_tools = _convert_tools(tools)
    if ag_tools:
        request["tools"] = ag_tools

    request["generationConfig"] = {"maxOutputTokens": 65536}

    return {
        "project": ANTIGRAVITY_DEFAULT_PROJECT,
        "model": model_id,
        "request": request,
        "requestType": "agent",
        "userAgent": "antigravity",
        "requestId": f"agent/{uuid.uuid4()}/{int(time.time() * 1000)}/0",
    }


class _ToolCallAccumulator:

    def __init__(self) -> None:
        self._calls: dict[str, dict] = {}
        self._order: list[str] = []

    def add(self, body: dict) -> None:
        call = body.get("functionCall") or {}
        if not isinstance(call, dict):
            return
        call_id = call.get("id") or ""
        if not call_id:
            return
        if call_id not in self._calls:
            self._calls[call_id] = {"name": "", "args": {}, "signature": ""}
            self._order.append(call_id)
        entry = self._calls[call_id]
        if call.get("name"):
            entry["name"] = call["name"]
        args = call.get("args")
        if isinstance(args, dict) and args:
            entry["args"] = args
        signature = body.get("thoughtSignature")
        if isinstance(signature, str) and signature:
            entry["signature"] = signature
            _remember_thought_signature(call_id, signature)

    def complete(self) -> list[dict]:
        results = []
        for call_id in self._order:
            call = self._calls[call_id]
            entry = {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call["args"]) if isinstance(call["args"], dict) else "{}",
                },
            }
            if call.get("signature"):
                entry["extra_content"] = {"google": {"thought_signature": call["signature"]}}
                _remember_thought_signature(f"{entry['function']['name']}|{entry['function']['arguments']}", call["signature"])
            results.append(entry)
        return results


def _chunk_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")


class AntigravityClient:

    def __init__(self, auth: AntigravityAuth) -> None:
        self.auth = auth

    def _headers(self, access_token: str) -> dict:
        return {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": ANTIGRAVITY_USER_AGENT,
            "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
            "Client-Metadata": json.dumps({
                "ideType": "ANTIGRAVITY",
                "platform": "PLATFORM_UNSPECIFIED",
                "pluginType": "GEMINI",
            }),
        }

    async def load_code_assist(self) -> dict:
        access_token = await self.auth.ensure_token()
        body = {"metadata": {"ideType": "ANTIGRAVITY"}}
        headers = self._headers(access_token)
        headers.pop("Accept", None)
        url = f"{antigravity_api_base()}/{ANTIGRAVITY_API_VERSION}:loadCodeAssist"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=body, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Antigravity loadCodeAssist failed with HTTP {resp.status_code}: {resp.text[:200]}"
            )
        try:
            return resp.json()
        except Exception:
            return {}

    async def fetch_available_models(self) -> list[dict]:
        access_token = await self.auth.ensure_token()
        body = {}
        headers = self._headers(access_token)
        headers.pop("Accept", None)
        url = f"{antigravity_api_base()}/{ANTIGRAVITY_API_VERSION}:fetchAvailableModels"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=body, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Antigravity model list failed with HTTP {resp.status_code}: {resp.text[:200]}"
            )
        try:
            data = resp.json()
        except Exception:
            return []
        models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(models, dict):
            return []
        catalogue: list[dict] = []
        for model_id, meta in models.items():
            if not isinstance(meta, dict):
                continue
            display = meta.get("displayName") or model_id
            entry = {
                "id": f"{ANTIGRAVITY_PREFIX}{model_id}",
                "provider": "Antigravity",
                "antigravity_model_id": model_id,
                "description": str(display),
                "supports_image": bool(meta.get("supportsImages", False)),
            }
            catalogue.append(entry)
        return catalogue

    async def list_models(self) -> list[dict]:
        try:
            models = await self.fetch_available_models()
        except Exception as e:
            logger.warning(f"Antigravity model list unavailable ({e}); using the built-in catalogue.")
            return [dict(m) for m in _MODEL_FALLBACKS]
        if models:
            return models
        return [dict(m) for m in _MODEL_FALLBACKS]

    async def stream_events(
        self,
        payload: dict,
        client: httpx.AsyncClient,
    ) -> AsyncIterator[tuple[str, Any]]:
        access_token = await self.auth.ensure_token()
        headers = self._headers(access_token)
        url = f"{antigravity_api_base()}/{ANTIGRAVITY_API_VERSION}:streamGenerateContent?alt=sse"
        req = client.build_request("POST", url, headers=headers, json=payload)
        response = await client.send(req, stream=True)
        if response.status_code != 200:
            body = await response.aread()
            detail = body.decode("utf-8", "replace")[:400]
            await response.aclose()
            if response.status_code == 403 and "VALIDATION_REQUIRED" in detail:
                raise RuntimeError(
                    "Antigravity rejected the account: Google requires this account to be "
                    "verified for Antigravity. Sign in again with a different personal Google "
                    f"account, or complete account verification at {detail}"
                )
            raise RuntimeError(f"Antigravity request failed with HTTP {response.status_code}: {detail}")

        buffer = ""
        try:
            async for chunk in response.aiter_text():
                buffer += chunk
                while True:
                    match = re.search(r"\r?\n\r?\n", buffer)
                    if match is None:
                        break
                    raw = buffer[: match.start()]
                    buffer = buffer[match.end():]
                    event = self._parse_sse(raw)
                    if event is not None:
                        yield event
            if buffer.strip():
                event = self._parse_sse(buffer)
                if event is not None:
                    yield event
        finally:
            await response.aclose()

    @staticmethod
    def _parse_sse(raw: str) -> Optional[tuple[str, Any]]:
        payload_text = ""
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                payload_text = line[5:].strip()
                break
        if not payload_text or payload_text == "[DONE]":
            return None
        try:
            body = json.loads(payload_text)
        except (TypeError, ValueError):
            return None
        return "message", body


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
        upstream_id = antigravity_upstream_model_id(model_id)
        await self.auth.ensure_token()

        own_client = client is None
        http_client = client or httpx.AsyncClient(timeout=300.0)
        try:
            payload = await build_antigravity_payload(
                messages, upstream_id, tools=tools, client=http_client
            )
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            tool_calls = _ToolCallAccumulator()
            usage: dict = {}

            async for _event, body in self.stream_events(payload, http_client):
                if not isinstance(body, dict):
                    continue
                response = body.get("response")
                if not isinstance(response, dict):
                    continue
                for candidate in response.get("candidates") or []:
                    if not isinstance(candidate, dict):
                        continue
                    content = candidate.get("content") or {}
                    for part in content.get("parts") or []:
                        if not isinstance(part, dict):
                            continue
                        if part.get("thought") is True:
                            thought = part.get("text")
                            if isinstance(thought, str) and thought:
                                reasoning_parts.append(thought)
                            continue
                        text = part.get("text")
                        if isinstance(text, str) and text:
                            content_parts.append(text)
                        fc = part.get("functionCall")
                        if isinstance(fc, dict):
                            tool_calls.add(part)
                meta = response.get("usageMetadata")
                if isinstance(meta, dict):
                    usage = meta
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

        prompt_tokens = int(usage.get("promptTokenCount") or 0) or estimate_tokens(messages)
        completion_tokens = int(usage.get("candidatesTokenCount") or 0)
        total_tokens = int(usage.get("totalTokenCount") or 0) or (prompt_tokens + completion_tokens)

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
                "total_tokens": total_tokens,
            },
        }

    async def stream_chat_completion(
        self,
        model_id: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> AsyncGenerator[bytes, None]:
        upstream_id = antigravity_upstream_model_id(model_id)
        await self.auth.ensure_token()

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
            payload = await build_antigravity_payload(
                messages, upstream_id, tools=tools, client=http_client
            )
            tool_calls = _ToolCallAccumulator()
            content_parts: list[str] = []
            usage: dict = {}

            yield _sse(base_chunk({"role": "assistant", "content": ""}))

            async for _event, body in self.stream_events(payload, http_client):
                if not isinstance(body, dict):
                    continue
                response = body.get("response")
                if not isinstance(response, dict):
                    continue
                for candidate in response.get("candidates") or []:
                    if not isinstance(candidate, dict):
                        continue
                    content = candidate.get("content") or {}
                    for part in content.get("parts") or []:
                        if not isinstance(part, dict):
                            continue
                        if part.get("thought") is True:
                            thought = part.get("text")
                            if isinstance(thought, str) and thought:
                                yield _sse(base_chunk({"reasoning_content": thought}))
                            continue
                        text = part.get("text")
                        if isinstance(text, str) and text:
                            content_parts.append(text)
                            yield _sse(base_chunk({"content": text}))
                        fc = part.get("functionCall")
                        if isinstance(fc, dict):
                            tool_calls.add(part)
                meta = response.get("usageMetadata")
                if isinstance(meta, dict):
                    usage = meta

            calls = tool_calls.complete()
            if calls:
                for call in calls:
                    delta = {
                        "index": 0,
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["function"]["name"],
                            "arguments": call["function"]["arguments"],
                        },
                    }
                    if call.get("extra_content"):
                        delta["extra_content"] = call["extra_content"]
                    yield _sse(base_chunk({"tool_calls": [delta]}))
                yield _sse(base_chunk({}, finish_reason="tool_calls"))
            else:
                yield _sse(base_chunk({}, finish_reason="stop"))

            prompt_tokens = int(usage.get("promptTokenCount") or 0) or estimate_tokens(messages)
            completion_tokens = int(usage.get("candidatesTokenCount") or 0)
            total_tokens = int(usage.get("totalTokenCount") or 0) or (prompt_tokens + completion_tokens)
            yield _sse({
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_id,
                "choices": [],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
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
