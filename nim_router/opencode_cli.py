"""OpenCode CLI provider.

OpenCode keeps a small set of free models available to its own CLI, but not to
the public Zen API (those ids answer ``401`` / ``429 FreeUsageLimitError`` when
called directly). This module drives a locally installed ``opencode`` binary so
the router can expose those models.

The provider only advertises models when the CLI is found on the machine that
runs the router. Requests are executed in an isolated workspace whose project
config defines a tool-less agent, because the default agent will happily run
shell commands and edit files.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from nim_router.logger import logger

OPENCODE_CLI_PROVIDER = "OpenCode CLI"
OPENCODE_CLI_PREFIX = "opencode-cli/"
OPENCODE_CLI_UPSTREAM_PREFIX = "opencode/"
OPENCODE_CLI_DEFAULT_MODEL = "beam-free"
OPENCODE_CLI_AGENT = "nim-chat"

OPENCODE_CLI_TIMEOUT = 180.0
OPENCODE_CLI_MODELS_TIMEOUT = 30.0
OPENCODE_CLI_MODEL_CACHE_TTL = 300.0
OPENCODE_CLI_BINARY_CACHE_TTL = 60.0

OPENCODE_CLI_INSTALL_HINT = (
    "Install the OpenCode CLI on this machine (https://opencode.ai) and make "
    "sure `opencode` is on PATH, or set OPENCODE_BIN to its absolute path."
)

_BINARY_CACHE: dict[str, Any] = {"path": None, "stamp": 0.0}
_MODELS_CACHE: dict[str, Any] = {"models": None, "stamp": 0.0}
_SPAWN_SEMAPHORE: asyncio.Semaphore | None = None

_AGENT_CONFIG = {
    "$schema": "https://opencode.ai/config.json",
    "agents": {
        OPENCODE_CLI_AGENT: {
            "mode": "primary",
            "description": "Plain text chat for NIM Router. All tools are disabled.",
            "permissions": [{"action": "*", "resource": "*", "effect": "deny"}],
            "system": (
                "You are a helpful assistant answering a plain chat completion "
                "request. Never use tools. Reply with text only."
            ),
        }
    },
}


class OpenCodeCliError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class OpenCodeCliUnavailable(OpenCodeCliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=503)


class OpenCodeCliAuthError(OpenCodeCliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=401)


# ─── Binary discovery ────────────────────────────────────────────────────────

def find_binary(force: bool = False) -> str:
    """Return the path to the local OpenCode CLI, or an empty string."""
    now = time.time()
    if (
        not force
        and _BINARY_CACHE["path"] is not None
        and now - _BINARY_CACHE["stamp"] < OPENCODE_CLI_BINARY_CACHE_TTL
    ):
        return _BINARY_CACHE["path"]

    candidates: list[str] = []
    env_bin = (os.getenv("OPENCODE_BIN") or "").strip()
    if env_bin:
        candidates.append(env_bin)
    on_path = shutil.which("opencode")
    if on_path:
        candidates.append(on_path)
    candidates.extend(
        [
            str(Path.home() / ".opencode" / "bin" / "opencode"),
            str(Path.home() / ".local" / "bin" / "opencode"),
            "/usr/local/bin/opencode",
            "/usr/bin/opencode",
        ]
    )

    chosen = ""
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            chosen = str(path)
            break

    _BINARY_CACHE.update({"path": chosen, "stamp": now})
    if chosen and force:
        logger.info(f"OpenCode CLI found at {chosen}.")
    return chosen


def is_available() -> bool:
    return bool(find_binary())


async def binary_info(force: bool = False) -> dict[str, Any]:
    """Return installation details for status endpoints and the dashboard."""
    binary = find_binary(force=force)
    info: dict[str, Any] = {
        "installed": bool(binary),
        "path": binary,
        "version": "",
        "install_hint": OPENCODE_CLI_INSTALL_HINT,
    }
    if not binary:
        return info
    try:
        proc = await asyncio.create_subprocess_exec(
            binary,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        info["version"] = stdout.decode("utf-8", "ignore").strip().splitlines()[0] if stdout else ""
    except Exception as exc:
        logger.debug(f"OpenCode CLI version check failed: {exc}")
    return info


# ─── Model mapping ───────────────────────────────────────────────────────────

def cli_model_id(model_id: str) -> str:
    """Map ``opencode-cli/<slug>`` to the CLI's ``opencode/<slug>``."""
    mid = (model_id or "").strip()
    for prefix in ("[OpenCode CLI] ", "[opencode cli] "):
        if mid.startswith(prefix):
            mid = mid[len(prefix):].strip()
    if mid.lower().startswith(OPENCODE_CLI_PREFIX):
        mid = mid[len(OPENCODE_CLI_PREFIX):].strip()
    if mid.startswith(OPENCODE_CLI_UPSTREAM_PREFIX):
        return mid
    return f"{OPENCODE_CLI_UPSTREAM_PREFIX}{mid or OPENCODE_CLI_DEFAULT_MODEL}"


def router_model_id(upstream_id: str) -> str:
    """Map ``opencode/<slug>`` to the router-facing ``opencode-cli/<slug>``."""
    slug = (upstream_id or "").strip()
    if slug.startswith(OPENCODE_CLI_UPSTREAM_PREFIX):
        slug = slug[len(OPENCODE_CLI_UPSTREAM_PREFIX):]
    return f"{OPENCODE_CLI_PREFIX}{slug}"


async def list_models(force: bool = False) -> list[dict]:
    """List the free models the local CLI exposes under the ``opencode`` provider."""
    now = time.time()
    if (
        not force
        and _MODELS_CACHE["models"] is not None
        and now - _MODELS_CACHE["stamp"] < OPENCODE_CLI_MODEL_CACHE_TTL
    ):
        return list(_MODELS_CACHE["models"])

    binary = find_binary(force=force)
    if not binary:
        raise OpenCodeCliUnavailable(
            f"OpenCode CLI is not installed on this machine. {OPENCODE_CLI_INSTALL_HINT}"
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            binary,
            "models",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=OPENCODE_CLI_MODELS_TIMEOUT
        )
    except asyncio.TimeoutError as exc:
        raise OpenCodeCliError("`opencode models` timed out", status_code=504) from exc
    except FileNotFoundError as exc:
        raise OpenCodeCliUnavailable(
            f"OpenCode CLI binary disappeared. {OPENCODE_CLI_INSTALL_HINT}"
        ) from exc

    if proc.returncode != 0:
        detail = (stderr or b"").decode("utf-8", "ignore").strip()[:300]
        raise OpenCodeCliError(f"`opencode models` failed (exit {proc.returncode}): {detail}")

    models: list[dict] = []
    seen: set[str] = set()
    for line in (stdout or b"").decode("utf-8", "ignore").splitlines():
        upstream = line.strip()
        if not upstream.startswith(OPENCODE_CLI_UPSTREAM_PREFIX):
            continue
        mid = router_model_id(upstream)
        if mid in seen:
            continue
        seen.add(mid)
        slug = mid[len(OPENCODE_CLI_PREFIX):]
        models.append(
            {
                "id": mid,
                "provider": OPENCODE_CLI_PROVIDER,
                "description": f"OpenCode CLI free model ({upstream})",
                "supports_image": False,
                "upstream": upstream,
                "slug": slug,
            }
        )

    _MODELS_CACHE.update({"models": models, "stamp": now})
    logger.info(f"OpenCode CLI: {len(models)} free model(s) available via {binary}.")
    return list(models)


# ─── Workspace / agent ───────────────────────────────────────────────────────

def workspace_dir() -> Path:
    """Return an isolated directory whose project config disables every tool."""
    raw = (os.getenv("OPENCODE_CLI_WORKSPACE") or "").strip()
    base = Path(raw).expanduser() if raw else Path.home() / ".cache" / "nim-router" / "opencode-cli"
    config_dir = base / ".opencode"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "opencode.json"
    desired = json.dumps(_AGENT_CONFIG, indent=2)
    try:
        current = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    except OSError:
        current = ""
    if current.strip() != desired.strip():
        config_path.write_text(desired + "\n", encoding="utf-8")
    return base


def _flatten_messages(messages: list[dict]) -> str:
    """Collapse an OpenAI message list into the single prompt the CLI accepts."""
    parts: list[str] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "user").lower()
        content = msg.get("content")
        if isinstance(content, list):
            content = " ".join(
                str(block.get("text") or "")
                for block in content
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            ).strip()
        text = str(content or "").strip()
        tool_calls = msg.get("tool_calls")
        if not text and tool_calls:
            text = json.dumps(tool_calls, ensure_ascii=False)
        if not text:
            continue
        if role == "system":
            parts.append(f"[System]\n{text}")
        elif role == "assistant":
            parts.append(f"[Assistant]\n{text}")
        elif role == "tool":
            parts.append(f"[Tool result]\n{text}")
        else:
            parts.append(f"[User]\n{text}")
    return "\n\n".join(parts).strip()


def _error_from_event(event: dict) -> OpenCodeCliError:
    error = event.get("error") or {}
    etype = str(error.get("type") or "")
    message = str(error.get("message") or "OpenCode CLI request failed")
    status = error.get("status")
    retry_ms = error.get("retryAfterMs")

    if etype == "provider.free-limit" or status == 429:
        retry_after = float(retry_ms) / 1000.0 if isinstance(retry_ms, (int, float)) else None
        return OpenCodeCliError(
            f"OpenCode free tier limit reached: {message}",
            status_code=429,
            retry_after=retry_after,
        )
    if etype == "provider.no-route" or "unavailable" in message.lower() or "not found" in message.lower():
        return OpenCodeCliError(message, status_code=404)
    if status in (401, 403) or "auth" in etype or "unauthorized" in message.lower():
        return OpenCodeCliAuthError(message)
    if status in (400, 402, 404, 429, 500, 502, 503):
        return OpenCodeCliError(message, status_code=int(status))
    return OpenCodeCliError(message, status_code=502)


def _get_semaphore() -> asyncio.Semaphore:
    global _SPAWN_SEMAPHORE
    if _SPAWN_SEMAPHORE is None:
        _SPAWN_SEMAPHORE = asyncio.Semaphore(3)
    return _SPAWN_SEMAPHORE


# ─── Execution ───────────────────────────────────────────────────────────────

async def _iter_text(
    model_id: str,
    messages: list[dict],
    timeout: float | None = None,
) -> AsyncGenerator[str, None]:
    """Run one CLI completion and yield text deltas as the model produces them."""
    binary = find_binary()
    if not binary:
        raise OpenCodeCliUnavailable(
            f"OpenCode CLI is not installed on this machine. {OPENCODE_CLI_INSTALL_HINT}"
        )

    prompt = _flatten_messages(messages)
    if not prompt:
        raise OpenCodeCliError("OpenCode CLI: empty prompt after flattening messages", status_code=400)

    upstream = cli_model_id(model_id)
    timeout = timeout or OPENCODE_CLI_TIMEOUT
    cwd = workspace_dir()
    # OpenCode resolves its project config from PWD, not the process cwd. If we
    # inherit the gateway's PWD the CLI looks in the wrong directory and cannot
    # find the tool-less agent defined in the workspace.
    env = {**os.environ, "PWD": str(cwd)}

    args = [
        binary,
        "run",
        "--standalone",
        "--agent",
        OPENCODE_CLI_AGENT,
        "--model",
        upstream,
        "--format",
        "json",
        prompt,
    ]

    async with _get_semaphore():
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                cwd=str(cwd),
                env=env,
                limit=4 * 1024 * 1024,
            )
        except FileNotFoundError as exc:
            raise OpenCodeCliUnavailable(
                f"OpenCode CLI binary cannot be executed. {OPENCODE_CLI_INSTALL_HINT}"
            ) from exc
        except OSError as exc:
            raise OpenCodeCliError(f"OpenCode CLI could not be started: {exc}") from exc

        emitted: dict[str, str] = {}
        emitted_any = False
        try:
            while True:
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
                except asyncio.TimeoutError as exc:
                    raise OpenCodeCliError(
                        f"OpenCode CLI timed out after {timeout:.0f}s", status_code=504
                    ) from exc
                if not line:
                    break
                raw = line.strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                kind = event.get("type")
                if kind == "error":
                    raise _error_from_event(event)
                if kind != "text":
                    continue
                part = event.get("part") or {}
                text = str(part.get("text") or "")
                if not text:
                    continue
                part_id = str(part.get("id") or "text")
                previous = emitted.get(part_id, "")
                if previous and text.startswith(previous):
                    delta = text[len(previous):]
                elif text == previous:
                    delta = ""
                else:
                    delta = text
                emitted[part_id] = text
                if delta:
                    emitted_any = True
                    yield delta

            returncode = await proc.wait()
            if returncode != 0 and not emitted_any:
                stderr = (await proc.stderr.read()).decode("utf-8", "ignore").strip()
                raise OpenCodeCliError(
                    f"OpenCode CLI exited with code {returncode}: {stderr[:400] or 'no output'}",
                    status_code=502,
                )
            if not emitted_any:
                raise OpenCodeCliError(
                    "OpenCode CLI returned no text. The model may have refused the prompt.",
                    status_code=502,
                )
        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                try:
                    await proc.wait()
                except Exception:
                    pass


def _sse_chunk(
    completion_id: str,
    created: int,
    model: str,
    content: str,
    finish_reason: str | None = None,
) -> bytes:
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content} if content else {},
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


async def stream_chat_completion(
    model_id: str,
    messages: list[dict],
    timeout: float | None = None,
    stats: dict | None = None,
) -> AsyncGenerator[bytes, None]:
    """Yield OpenAI-style SSE chunks for a CLI completion."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    model_label = router_model_id(cli_model_id(model_id))

    prompt_chars = sum(
        len(str(m.get("content") or "")) for m in (messages or []) if isinstance(m, dict)
    )
    completion_chars = 0

    async for delta in _iter_text(model_id, messages, timeout=timeout):
        completion_chars += len(delta)
        yield _sse_chunk(completion_id, created, model_label, delta)

    if stats is not None:
        stats["prompt_tokens"] = max(1, prompt_chars // 4)
        stats["completion_tokens"] = max(1, completion_chars // 4)

    yield _sse_chunk(completion_id, created, model_label, "", finish_reason="stop")
    yield b"data: [DONE]\n\n"


async def create_chat_completion(
    model_id: str,
    messages: list[dict],
    timeout: float | None = None,
) -> dict:
    """Non-streaming completion: collect the CLI's text into one response."""
    parts: list[str] = []
    async for delta in _iter_text(model_id, messages, timeout=timeout):
        parts.append(delta)

    text = "".join(parts)
    prompt_chars = sum(
        len(str(m.get("content") or "")) for m in (messages or []) if isinstance(m, dict)
    )
    prompt_tokens = max(1, prompt_chars // 4)
    completion_tokens = max(1, len(text) // 4)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": router_model_id(cli_model_id(model_id)),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
