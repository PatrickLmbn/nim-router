import asyncio
import base64
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import httpx

from nim_router.logger import logger
from nim_router.deepseek_pow import build_pow_header

DEEPSEEK_WEB_BASE = "https://chat.deepseek.com/api/v0"
DEEPSEEK_HIF_QUERY_URL = "https://hif-leim.deepseek.com/query"
DEEPSEEK_HIF_DLIQ_HOST = "hif-dliq.deepseek.com"
DEEPSEEK_WEB_PREFIX = "deepseek-web/"
DEEPSEEK_WEB_COMPLETION_PATH = "/api/v0/chat/completion"
_DSML_TOKEN = "\uff5cDSML\uff5c"

DEEPSEEK_WEB_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36"
)

_BROWSER_PROFILES = (
    "~/.var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/Default",
    "~/.config/BraveSoftware/Brave-Browser/Default",
    "~/.config/google-chrome/Default",
    "~/.config/chromium/Default",
)

_LEVELDB_TOKEN_JSON = re.compile(rb'"userToken"\s*:\s*"([A-Za-z0-9_\-]{16,})"')
_LEVELDB_DS_SESSION_JSON = re.compile(rb'"ds_session_id"\s*:\s*"([A-Za-z0-9_\-]{16,})"')
_LEVELDB_RUN = re.compile(rb'[A-Za-z0-9_\-]{32,256}')

_TOKEN_CACHE: dict[str, Any] = {"value": "", "ds_session_id": "", "source": "", "stamp": 0.0}
_TOKEN_TTL = 300.0


def _read_env_token() -> str:
    return (os.getenv("DEEPSEEK_WEB_TOKEN") or "").strip()


def _read_env_session() -> str:
    return (os.getenv("DEEPSEEK_WEB_DS_SESSION_ID") or "").strip()


def _leveldb_binary_value(blob: bytes, key: bytes) -> str:
    start = 0
    while True:
        idx = blob.find(key, start)
        if idx < 0:
            return ""
        if blob[idx + len(key):idx + len(key) + 1] not in (b"s",):
            window = blob[idx + len(key):idx + len(key) + 96]
            for match in _LEVELDB_RUN.finditer(window):
                return match.group(0).decode("ascii", "ignore")
        start = idx + 1


def _scan_leveldb(profile: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    storage = profile / "Local Storage" / "leveldb"
    if not storage.is_dir():
        return found
    candidates = sorted(
        list(storage.glob("*.ldb")) + list(storage.glob("*.log")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            blob = path.read_bytes()
        except Exception:
            continue
        if "userToken" not in found:
            match = _LEVELDB_TOKEN_JSON.search(blob)
            if match:
                found["userToken"] = match.group(1).decode("ascii", "ignore")
            else:
                binary = _leveldb_binary_value(blob, b"userToken")
                if binary:
                    found["userToken"] = binary
        if "ds_session_id" not in found:
            match = _LEVELDB_DS_SESSION_JSON.search(blob)
            if match:
                found["ds_session_id"] = match.group(1).decode("ascii", "ignore")
            else:
                binary = _leveldb_binary_value(blob, b"ds_session_id")
                if binary:
                    found["ds_session_id"] = binary
        if "userToken" in found and "ds_session_id" in found:
            break
    return found


def _scan_cookies(profile: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    db = profile / "Cookies"
    if not db.is_file():
        return found
    try:
        import sqlite3
        uri = f"file:{db}?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        try:
            rows = conn.execute(
                "SELECT name, value FROM cookies WHERE host_key LIKE '%deepseek%'"
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return found
    for name, value in rows:
        if not value:
            continue
        if name in ("ds_session_id", "userToken"):
            found[name] = value
    return found


def extract_browser_credentials() -> dict[str, str]:
    for raw in _BROWSER_PROFILES:
        profile = Path(raw).expanduser()
        if not profile.is_dir():
            continue
        merged = _scan_leveldb(profile)
        for key, value in _scan_cookies(profile).items():
            merged.setdefault(key, value)
        if merged.get("userToken"):
            merged["source"] = str(profile)
            return merged
    return {}


def resolve_credentials(force: bool = False) -> dict[str, str]:
    now = time.time()
    if not force and _TOKEN_CACHE["value"] and (now - _TOKEN_CACHE["stamp"]) < _TOKEN_TTL:
        return {
            "token": _TOKEN_CACHE["value"],
            "ds_session_id": _TOKEN_CACHE["ds_session_id"],
            "source": _TOKEN_CACHE["source"],
        }

    token = _read_env_token()
    session = _read_env_session()
    source = "env" if token else ""

    if not token:
        browser = extract_browser_credentials()
        token = browser.get("userToken", "")
        session = session or browser.get("ds_session_id", "")
        if token:
            source = browser.get("source", "browser")

    _TOKEN_CACHE.update({"value": token, "ds_session_id": session, "source": source, "stamp": now})
    return {"token": token, "ds_session_id": session, "source": source}


def deepseek_web_upstream_model_id(model_id: str) -> str:
    mid = (model_id or "").strip()
    if mid.startswith("[DeepSeek Web] "):
        mid = mid[len("[DeepSeek Web] "):].strip()
    if mid.lower().startswith(DEEPSEEK_WEB_PREFIX):
        mid = mid[len(DEEPSEEK_WEB_PREFIX):].strip()
    return mid or "chat"


def _client_headers(token: str, accept: str = "application/json") -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": DEEPSEEK_WEB_USER_AGENT,
        "x-app-version": "2.0.0",
        "x-client-platform": "web",
        "x-client-version": "2.4.0",
        "x-client-locale": "en_US",
        "referer": "https://chat.deepseek.com/a/chat/",
        "origin": "https://chat.deepseek.com",
        "accept": accept,
    }


def _unwrap_biz(payload: dict) -> dict:
    data = payload.get("data")
    if not isinstance(data, dict):
        return {}
    biz = data.get("biz_data")
    return biz if isinstance(biz, dict) else {}


async def fetch_hif_tokens(client: httpx.AsyncClient) -> dict[str, str]:
    tokens = {"leim": "", "dliq": ""}
    try:
        resp = await client.get(
            DEEPSEEK_HIF_QUERY_URL,
            headers={"Host": DEEPSEEK_HIF_DLIQ_HOST, "User-Agent": DEEPSEEK_WEB_USER_AGENT},
            timeout=10.0,
        )
        if resp.status_code == 200:
            tokens["leim"] = str((resp.json().get("biz_data") or {}).get("value") or "")
    except Exception as exc:
        logger.warning(f"DeepSeek Web: hif leim fetch failed: {exc}")
    if not tokens["leim"]:
        return tokens
    try:
        resp = await client.get(
            "https://hif-dliq.deepseek.com/query",
            headers={"User-Agent": DEEPSEEK_WEB_USER_AGENT},
            timeout=10.0,
        )
        if resp.status_code == 200:
            tokens["dliq"] = str((resp.json().get("biz_data") or {}).get("value") or "")
    except Exception as exc:
        logger.warning(f"DeepSeek Web: hif dliq fetch failed: {exc}")
    return tokens


async def fetch_pow_challenge(client: httpx.AsyncClient, token: str) -> dict:
    resp = await client.post(
        f"{DEEPSEEK_WEB_BASE}/chat/create_pow_challenge",
        json={"target_path": DEEPSEEK_WEB_COMPLETION_PATH},
        headers=_client_headers(token),
        timeout=20.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"DeepSeek Web: pow challenge failed with HTTP {resp.status_code}: {resp.text[:200]}")
    challenge = _unwrap_biz(resp.json()).get("challenge")
    if not isinstance(challenge, dict):
        raise RuntimeError("DeepSeek Web: pow challenge payload missing")
    return challenge


async def create_chat_session(client: httpx.AsyncClient, token: str, thinking_enabled: bool = False) -> str:
    body: dict = {"character_id": None}
    if thinking_enabled:
        body["thinking_enabled"] = True
    resp = await client.post(
        f"{DEEPSEEK_WEB_BASE}/chat_session/create",
        json=body,
        headers=_client_headers(token),
        timeout=20.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"DeepSeek Web: session create failed with HTTP {resp.status_code}: {resp.text[:200]}")
    session = (_unwrap_biz(resp.json()).get("chat_session") or {}).get("id") or ""
    if not session:
        raise RuntimeError("DeepSeek Web: session create returned no id")
    return str(session)


async def list_models() -> list[dict]:
    credentials = resolve_credentials()
    token = credentials["token"]
    if not token:
        raise RuntimeError("DeepSeek Web is not configured. Set DEEPSEEK_WEB_TOKEN or sign in to chat.deepseek.com in a local browser.")
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{DEEPSEEK_WEB_BASE}/users/current",
            headers=_client_headers(token),
        )
    if resp.status_code != 200:
        raise RuntimeError(f"DeepSeek Web auth check failed with HTTP {resp.status_code}: {resp.text[:200]}")
    return [
        {
            "id": f"{DEEPSEEK_WEB_PREFIX}chat",
            "provider": "DeepSeek Web",
            "description": "DeepSeek Web chat (default model)",
            "supports_image": False,
        },
        {
            "id": f"{DEEPSEEK_WEB_PREFIX}reasoner",
            "provider": "DeepSeek Web",
            "description": "DeepSeek Web chat with thinking enabled",
            "supports_image": False,
        },
    ]


def _tool_specs(tools: Optional[list[dict]]) -> list[dict]:
    specs: list[dict] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") if tool.get("type") == "function" else tool
        if not isinstance(fn, dict) or not fn.get("name"):
            continue
        specs.append({
            "name": str(fn["name"]),
            "description": str(fn.get("description") or ""),
            "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return specs


def _tools_prompt(tools: Optional[list[dict]], tool_choice: Any = None) -> str:
    if tool_choice == "none":
        return ""
    specs = _tool_specs(tools)
    if not specs:
        return ""
    lines = [
        "## Tools",
        "You have access to these tools:",
        json.dumps(specs, ensure_ascii=False),
        "",
        "Invoke tools by writing a block in this exact format:",
        f"<{_DSML_TOKEN}tool_calls>",
        f'<{_DSML_TOKEN}invoke name="$TOOL_NAME">',
        f'<{_DSML_TOKEN}parameter name="$PARAMETER_NAME" string="true">$PARAMETER_VALUE</{_DSML_TOKEN}parameter>',
        f"</{_DSML_TOKEN}invoke>",
        f"</{_DSML_TOKEN}tool_calls>",
        "Repeat the invoke block inside the same tool_calls block for each call.",
        'Use string="true" for literal text and string="false" for numbers, booleans, arrays and objects.',
        "Write nothing else when calling tools. Tool results arrive as "
        '"Tool result (<name>): ..." messages; use them to answer the user.',
    ]
    if tool_choice == "required":
        lines.append("You MUST call at least one tool in this reply.")
    return "\n".join(lines)


def _assistant_calls_text(msg: dict) -> str:
    blocks: list[str] = []
    for call in msg.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        fn = call.get("function") or {}
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except (TypeError, ValueError):
                args = {}
        if not isinstance(args, dict):
            args = {}
        lines = [f'<{_DSML_TOKEN}invoke name="{name}">']
        for key, value in args.items():
            if isinstance(value, str):
                lines.append(
                    f'<{_DSML_TOKEN}parameter name="{key}" string="true">{value}</{_DSML_TOKEN}parameter>'
                )
            else:
                lines.append(
                    f'<{_DSML_TOKEN}parameter name="{key}" string="false">'
                    f'{json.dumps(value, ensure_ascii=False)}</{_DSML_TOKEN}parameter>'
                )
        lines.append(f"</{_DSML_TOKEN}invoke>")
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    return "\n".join(blocks)


def _flatten_messages(
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    tool_choice: Any = None,
) -> str:
    tool_names: dict[str, str] = {}
    for msg in messages or []:
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        for call in msg.get("tool_calls") or []:
            if isinstance(call, dict) and call.get("id"):
                fn = call.get("function") or {}
                if fn.get("name"):
                    tool_names[str(call["id"])] = str(fn["name"])

    system_parts: list[str] = []
    turns: list[str] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "user")
        content = msg.get("content")
        if isinstance(content, list):
            text = "".join(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict)
            )
        else:
            text = str(content or "")
        if role == "assistant":
            if text.strip():
                turns.append(f"Assistant: {text.strip()}")
            calls_text = _assistant_calls_text(msg)
            if calls_text:
                turns.append(f"Assistant: {calls_text}")
            continue
        if not text.strip():
            continue
        if role == "system":
            system_parts.append(text.strip())
        elif role == "tool":
            name = msg.get("name") or tool_names.get(str(msg.get("tool_call_id") or "")) or "tool"
            turns.append(f"Tool result ({name}): {text.strip()}")
        else:
            turns.append(text.strip())
    tools_prompt = _tools_prompt(tools, tool_choice)
    if tools_prompt:
        system_parts.insert(0, tools_prompt)
    prompt = "\n\n".join(turns) if turns else ""
    if system_parts:
        prompt = "\n\n".join(system_parts) + "\n\n" + prompt
    return prompt


def _chunk_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")


class _StreamState:

    def __init__(self) -> None:
        self.text: list[str] = []
        self.thinking: list[str] = []
        self.usage = 0
        self.finished = False
        self._last_type = "RESPONSE"

    def _classify(self, fragment: dict) -> Optional[tuple[str, str]]:
        content = str(fragment.get("content", ""))
        if not content:
            return None
        if fragment.get("type") == "THINK":
            self.thinking.append(content)
            return ("reasoning_content", content)
        if "type" in fragment:
            self.text.append(content)
            return ("content", content)
        return None

    def feed(self, payload: dict) -> list[tuple[str, str]]:
        events: list[tuple[str, str]] = []
        value = payload.get("v")
        path = payload.get("p")
        op = payload.get("o")

        if isinstance(value, dict):
            response = value.get("response")
            if not isinstance(response, dict):
                return events
            fragments = response.get("fragments") or []
            if fragments:
                last = fragments[-1]
                if isinstance(last, dict) and last.get("type") in ("THINK", "RESPONSE"):
                    self._last_type = str(last["type"])
            for fragment in fragments:
                if isinstance(fragment, dict):
                    event = self._classify(fragment)
                    if event:
                        events.append(event)
            return events

        if isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                if item.get("p") == "accumulated_token_usage":
                    try:
                        self.usage = int(item.get("v") or 0)
                    except Exception:
                        pass
                    continue
                if item.get("type") in ("THINK", "RESPONSE"):
                    self._last_type = str(item["type"])
                    event = self._classify(item)
                    if event:
                        events.append(event)
            return events

        if isinstance(value, str):
            if path and path.endswith("/content"):
                if value == "FINISHED":
                    self.finished = True
                else:
                    event = self._classify({"type": self._last_type, "content": value})
                    if event:
                        events.append(event)
                return events
            if op == "APPEND":
                event = self._classify({"type": self._last_type, "content": value})
                if event:
                    events.append(event)
                return events
            if path is None:
                if value == "FINISHED":
                    self.finished = True
                else:
                    event = self._classify({"type": self._last_type, "content": value})
                    if event:
                        events.append(event)
            return events

        return events


_FENCE = "```"
_DSML_MARK = re.compile(r"<\s*(/?)\s*[\uff5c|]{1,2}\s*DSML\s*[\uff5c|]{1,2}\s*")
_DSML_START = re.compile(r"<\s*[\uff5c|]{1,2}\s*DSML\s*[\uff5c|]{1,2}")
_HOLDBACK = 16


def _normalize_dsml(raw: str) -> str:
    return _DSML_MARK.sub(lambda m: "\x02" if m.group(1) else "\x01", raw)


def _parse_dsml_calls(raw: str) -> list[dict]:
    text = _normalize_dsml(raw)
    if "\x01invoke" not in text:
        return []
    calls: list[dict] = []
    for invoke in re.finditer(
        r"\x01invoke\s+name\s*=\s*\"([^\"]+)\"\s*>(.*?)(?=\x01invoke\s+name\s*=|\Z)",
        text,
        re.S,
    ):
        name = invoke.group(1).strip()
        if not name:
            continue
        body = invoke.group(2)
        stop = body.find("\x02invoke>")
        if stop != -1:
            body = body[:stop]
        args: dict = {}
        for param in re.finditer(
            r"\x01parameter\s+name\s*=\s*\"([^\"]+)\"\s*(?:string\s*=\s*\"(true|false)\"\s*)?>(.*?)(?=\x01parameter\s+name\s*=|\Z)",
            body,
            re.S,
        ):
            key = param.group(1).strip()
            flag = param.group(2)
            value = param.group(3)
            cut = value.find("\x02parameter>")
            if cut != -1:
                value = value[:cut]
            value = value.strip()
            if flag != "true":
                try:
                    value = json.loads(value)
                except (TypeError, ValueError):
                    pass
            args[key] = value
        calls.append({
            "id": f"call_{uuid.uuid4().hex[:24]}",
            "name": name,
            "arguments": args,
        })
    return calls


def _parse_json_calls(raw: str) -> list[dict]:
    text = raw.strip()
    if text.endswith(_FENCE):
        text = text[: -len(_FENCE)].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(text[start:end + 1])
    except (TypeError, ValueError):
        return []
    if isinstance(data, list):
        raw_calls = data
    elif isinstance(data, dict):
        raw_calls = data.get("tool_calls")
        if raw_calls is None and data.get("name"):
            raw_calls = [data]
    else:
        return []
    if not isinstance(raw_calls, list):
        return []
    calls: list[dict] = []
    for call in raw_calls:
        if not isinstance(call, dict):
            continue
        fn = call.get("function") if isinstance(call.get("function"), dict) else call
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except (TypeError, ValueError):
                args = {}
        calls.append({
            "id": f"call_{uuid.uuid4().hex[:24]}",
            "name": name,
            "arguments": args if isinstance(args, dict) else {},
        })
    return calls


def _parse_tool_calls(raw: str) -> list[dict]:
    calls = _parse_json_calls(raw)
    if calls:
        return calls
    return _parse_dsml_calls(raw)


class _ToolCallExtractor:

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._pending = ""
        self._payload = ""
        self._collecting = False

    def feed(self, text: str) -> list[str]:
        if not self.enabled:
            return [text] if text else []
        self._pending += text
        if self._collecting:
            self._payload += self._pending
            self._pending = ""
            return []
        idx = self._pending.find(_FENCE)
        dsml = _DSML_START.search(self._pending)
        if idx == -1 and dsml is None:
            if len(self._pending) <= _HOLDBACK:
                return []
            emit = self._pending[:-_HOLDBACK]
            self._pending = self._pending[-_HOLDBACK:]
            return [emit] if emit else []
        if dsml is not None and (idx == -1 or dsml.start() <= idx):
            emit = self._pending[:dsml.start()]
            self._collecting = True
            self._payload = self._pending[dsml.start():]
            self._pending = ""
            return [emit] if emit else []
        rest = self._pending[idx + len(_FENCE):]
        probe = rest.strip()
        if not probe or probe in ("j", "js", "jso", "json"):
            return []
        body = probe[4:].lstrip() if probe.lower().startswith("json") else probe
        if not body:
            return []
        if not body.startswith("{"):
            emit = self._pending[: idx + len(_FENCE)]
            remainder = self._pending[idx + len(_FENCE):]
            self._pending = ""
            self.enabled = False
            return [emit + remainder] if (emit or remainder) else []
        emit = self._pending[:idx]
        self._collecting = True
        self._payload = rest
        self._pending = ""
        return [emit] if emit else []

    def finish(self) -> tuple[list[str], list[dict]]:
        pending, self._pending = self._pending, ""
        raw, self._payload = self._payload, ""
        if not self._collecting:
            return ([pending] if pending else []), []
        calls = _parse_tool_calls(raw)
        if calls:
            return [], calls
        return [raw], []


async def stream_chat_completion(
    model_id: str,
    messages: list[dict],
    client: httpx.AsyncClient,
    thinking_enabled: bool = False,
    tools: Optional[list[dict]] = None,
    tool_choice: Any = None,
) -> AsyncGenerator[bytes, None]:
    credentials = resolve_credentials()
    token = credentials["token"]
    if not token:
        raise RuntimeError("DeepSeek Web is not configured. Set DEEPSEEK_WEB_TOKEN or sign in to chat.deepseek.com in a local browser.")

    prompt = _flatten_messages(messages, tools, tool_choice)
    if not prompt.strip():
        raise RuntimeError("DeepSeek Web: empty prompt after flattening messages")

    challenge = await fetch_pow_challenge(client, token)
    pow_header = await asyncio.to_thread(build_pow_header, challenge, DEEPSEEK_WEB_COMPLETION_PATH)
    hif = await fetch_hif_tokens(client)

    session_id = await create_chat_session(client, token, thinking_enabled=thinking_enabled)

    headers = _client_headers(token, accept="text/event-stream")
    headers["x-ds-pow-response"] = pow_header
    if hif.get("leim"):
        headers["x-hif-leim"] = hif["leim"]
    if hif.get("dliq"):
        headers["x-hif-dliq"] = hif["dliq"]

    body: dict = {
        "chat_session_id": session_id,
        "prompt": prompt,
        "ref_file_ids": [],
        "thinking_enabled": bool(thinking_enabled),
        "search_enabled": False,
    }

    completion_id = _chunk_id()
    created = int(time.time())
    state = _StreamState()
    extractor = _ToolCallExtractor(bool(_tool_specs(tools)))

    def base_chunk(delta: dict, finish_reason: Optional[str] = None) -> dict:
        return {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_id,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }

    request = client.build_request("POST", f"{DEEPSEEK_WEB_BASE}/chat/completion", headers=headers, json=body)
    response = await client.send(request, stream=True)
    if response.status_code != 200:
        detail = (await response.aread()).decode("utf-8", "replace")[:400]
        await response.aclose()
        raise RuntimeError(f"DeepSeek Web completion failed with HTTP {response.status_code}: {detail}")

    yield _sse(base_chunk({"role": "assistant", "content": ""}))

    try:
        async for line in response.aiter_lines():
            if not line:
                continue
            if line.startswith("event: "):
                if line[7:].strip() == "close":
                    break
                continue
            if not line.startswith("data: "):
                continue
            raw = line[6:].strip()
            if raw == "[DONE]":
                break
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            for kind, text in state.feed(payload):
                if kind == "reasoning_content":
                    yield _sse(base_chunk({"reasoning_content": text}))
                else:
                    for piece in extractor.feed(text):
                        if piece:
                            yield _sse(base_chunk({"content": piece}))
    finally:
        await response.aclose()

    leftover, calls = extractor.finish()
    for piece in leftover:
        if piece:
            yield _sse(base_chunk({"content": piece}))

    for index, call in enumerate(calls):
        yield _sse(base_chunk({"tool_calls": [{
            "index": index,
            "id": call["id"],
            "type": "function",
            "function": {"name": call["name"], "arguments": ""},
        }]}))
        yield _sse(base_chunk({"tool_calls": [{
            "index": index,
            "function": {"arguments": json.dumps(call["arguments"], ensure_ascii=False)},
        }]}))

    yield _sse(base_chunk({}, finish_reason="tool_calls" if calls else "stop"))

    prompt_tokens = max(1, int(len(prompt) / 3.8))
    completion_tokens = state.usage or max(1, int(len("".join(state.text)) / 3.8))
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


async def create_chat_completion(
    model_id: str,
    messages: list[dict],
    client: httpx.AsyncClient,
    thinking_enabled: bool = False,
    tools: Optional[list[dict]] = None,
    tool_choice: Any = None,
) -> dict:
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    usage_total = 0
    tool_calls: dict[int, dict] = {}
    prompt = _flatten_messages(messages, tools, tool_choice)

    async for chunk in stream_chat_completion(
        model_id, messages, client, thinking_enabled=thinking_enabled, tools=tools, tool_choice=tool_choice
    ):
        if not chunk.startswith(b"data: "):
            continue
        raw = chunk[6:].strip()
        if raw == b"[DONE]":
            break
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        choices = payload.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            if delta.get("content"):
                text_parts.append(str(delta["content"]))
            if delta.get("reasoning_content"):
                reasoning_parts.append(str(delta["reasoning_content"]))
            for call in delta.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                try:
                    index = int(call.get("index") or 0)
                except (TypeError, ValueError):
                    index = 0
                entry = tool_calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                if call.get("id"):
                    entry["id"] = str(call["id"])
                fn = call.get("function") or {}
                if fn.get("name"):
                    entry["name"] = str(fn["name"])
                if fn.get("arguments"):
                    entry["arguments"] += str(fn["arguments"])
        usage = payload.get("usage") or {}
        if usage.get("total_tokens"):
            usage_total = int(usage["total_tokens"])

    text = "".join(text_parts)
    prompt_tokens = max(1, int(len(prompt) / 3.8))
    completion_tokens = max(1, int(len(text) / 3.8)) if text else 0
    message: dict = {"role": "assistant", "content": text}
    if reasoning_parts:
        message["reasoning_content"] = "".join(reasoning_parts)
    calls = [
        {
            "id": entry["id"] or f"call_{uuid.uuid4().hex[:24]}",
            "type": "function",
            "function": {"name": entry["name"], "arguments": entry["arguments"] or "{}"},
        }
        for _, entry in sorted(tool_calls.items())
    ]
    if calls:
        message["tool_calls"] = calls
    return {
        "id": _chunk_id(),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if calls else "stop"}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": usage_total or (prompt_tokens + completion_tokens),
        },
    }
