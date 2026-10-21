import json
import os
import re
import shutil
import subprocess
import urllib.parse
from typing import Optional

from nim_router.logger import logger

CLIENT_ID_RE = re.compile(r"\d{10,}-[a-z0-9]{20,}\.apps\.googleusercontent\.com")
CLIENT_SECRET_RE = re.compile(r"GOCSPX-[A-Za-z0-9_-]{28}")

ENV_CLIENT_ID = "ANTIGRAVITY_CLIENT_ID"
ENV_CLIENT_SECRET = "ANTIGRAVITY_CLIENT_SECRET"

TOKEN_URL = "https://oauth2.googleapis.com/token"
REQUIRED_SCOPE = "https://www.googleapis.com/auth/aicode"

AGY_BINARY_PATHS = (
    "~/.gemini/bin/agy",
    "~/.gemini/bin/antigravity",
    "/usr/local/bin/agy",
    "/usr/bin/agy",
)

AGY_BINARIES = ("agy", "antigravity")


def _candidate_binaries() -> list[str]:
    paths: list[str] = []
    for name in AGY_BINARIES:
        found = shutil.which(name)
        if found:
            paths.append(found)
    for candidate in AGY_BINARY_PATHS:
        expanded = os.path.expanduser(candidate)
        if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            paths.append(expanded)
    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def _scan_binary(path: str) -> tuple[list[str], list[str]]:
    try:
        proc = subprocess.run(
            ["strings", "-a", path],
            capture_output=True,
            timeout=180,
        )
    except Exception:
        return [], []
    text = proc.stdout.decode("utf-8", "replace")
    client_ids: list[str] = []
    for found in CLIENT_ID_RE.findall(text):
        if found not in client_ids:
            client_ids.append(found)
    secrets: list[str] = []
    for found in CLIENT_SECRET_RE.findall(text):
        if found not in secrets:
            secrets.append(found)
    return client_ids, secrets


def _post_token(payload: str) -> dict:
    try:
        proc = subprocess.run(
            [
                "curl",
                "-s",
                "-X",
                "POST",
                TOKEN_URL,
                "-H",
                "Content-Type: application/x-www-form-urlencoded",
                "--data",
                payload,
            ],
            capture_output=True,
            timeout=30,
        )
        return json.loads(proc.stdout.decode("utf-8", "replace"))
    except Exception:
        return {}


def _pair_is_valid(client_id: str, client_secret: str) -> bool:
    payload = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": "invalid-probe",
            "grant_type": "refresh_token",
        }
    )
    return _post_token(payload).get("error") == "invalid_grant"


def _pair_supports_scope(client_id: str, client_secret: str, scope: str) -> bool:
    payload = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": "invalid-probe",
            "grant_type": "refresh_token",
            "scope": scope,
        }
    )
    error = _post_token(payload).get("error", "")
    return error in ("invalid_grant",)


def _from_config() -> tuple[str, str]:
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config",
        "antigravity_oauth.json",
    )
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return str(data.get("client_id") or ""), str(data.get("client_secret") or "")
    except Exception:
        return "", ""


_cached: Optional[tuple[str, str]] = None


def resolve_oauth_client() -> tuple[str, str]:
    global _cached
    if _cached is not None:
        return _cached

    env_id = (os.environ.get(ENV_CLIENT_ID) or "").strip()
    env_secret = (os.environ.get(ENV_CLIENT_SECRET) or "").strip()
    if env_id and env_secret:
        _cached = (env_id, env_secret)
        return _cached

    cfg_id, cfg_secret = _from_config()
    if cfg_id and cfg_secret:
        _cached = (cfg_id, cfg_secret)
        return _cached

    fallback: tuple[str, str] = ("", "")
    for binary in _candidate_binaries():
        client_ids, secrets = _scan_binary(binary)
        for client_id in client_ids:
            for client_secret in secrets:
                if not _pair_is_valid(client_id, client_secret):
                    continue
                if _pair_supports_scope(client_id, client_secret, REQUIRED_SCOPE):
                    logger.info("Resolved Antigravity OAuth client from %s.", binary)
                    _cached = (client_id, client_secret)
                    return _cached
                if not fallback[0]:
                    fallback = (client_id, client_secret)

    if fallback[0]:
        logger.warning(
            "Antigravity OAuth client from the installed CLI cannot grant the %s scope.",
            REQUIRED_SCOPE,
        )
        _cached = fallback
        return _cached

    if env_id or env_secret:
        logger.warning(
            "Antigravity OAuth client is partially configured. Set both %s and %s.",
            ENV_CLIENT_ID,
            ENV_CLIENT_SECRET,
        )
    else:
        logger.warning(
            "Antigravity OAuth client was not found. Install the Antigravity CLI, or set %s and %s.",
            ENV_CLIENT_ID,
            ENV_CLIENT_SECRET,
        )

    _cached = (env_id, env_secret)
    return _cached


def get_client_id() -> str:
    return resolve_oauth_client()[0]


def get_client_secret() -> str:
    return resolve_oauth_client()[1]
