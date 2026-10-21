
import asyncio
import base64
import hashlib
import json
import os
import secrets
import stat
import time
import urllib.parse
from typing import Optional

import httpx

from nim_router.logger import logger

ANTIGRAVITY_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
ANTIGRAVITY_TOKEN_URL = "https://oauth2.googleapis.com/token"
ANTIGRAVITY_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo?alt=json"

from nim_router.antigravity_oauth import get_client_id as _get_client_id, get_client_secret as _get_client_secret

ANTIGRAVITY_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
    "https://www.googleapis.com/auth/aicode",
)

ANTIGRAVITY_CALLBACK_PORT = 51121
ANTIGRAVITY_CALLBACK_PATH = "/oauth-callback"
ANTIGRAVITY_CALLBACK_HOST = "localhost"

CALLBACK_PORT_CANDIDATES = (51121, 3128, 4649, 6588, 8008, 9091, 49153, 50153)

LOOPBACK_HOSTS = ("127.0.0.1", "::1")

LOGIN_TIMEOUT_SECONDS = 600

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CREDENTIALS_DIR = os.path.join(_BASE_DIR, "config")
_CREDENTIALS_FILE = os.path.join(_CREDENTIALS_DIR, "antigravity_credentials.json")

_SUCCESS_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Antigravity sign-in complete</title>
<style>body{font-family:system-ui,-apple-system,sans-serif;background:#0b0b0d;color:#f5f5f7;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.card{text-align:center;max-width:420px;padding:40px}
h1{font-size:20px;font-weight:600;margin:0 0 8px}
p{color:#a1a1a6;font-size:14px;line-height:1.5;margin:0}
.dot{color:#4285f4}</style></head>
<body><div class="card"><h1><span class="dot">&#9679;</span> Antigravity connected</h1>
<p>Google sign-in succeeded. You can close this tab and return to the router.</p>
</div></body></html>"""

_ERROR_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Antigravity sign-in failed</title>
<style>body{font-family:system-ui,-apple-system,sans-serif;background:#0b0b0d;color:#f5f5f7;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.card{text-align:center;max-width:460px;padding:40px}
h1{font-size:20px;font-weight:600;margin:0 0 8px;color:#ff453a}
p{color:#a1a1a6;font-size:14px;line-height:1.5;margin:0}</style></head>
<body><div class="card"><h1>Antigravity sign-in failed</h1><p>__MESSAGE__</p></div></body></html>"""


def _error_page(message: str) -> str:
    return _ERROR_PAGE.replace("__MESSAGE__", _escape(message))


class AntigravityLoginError(RuntimeError):
    pass




def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def generate_pkce() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def build_auth_url(state: str, code_challenge: str, redirect_uri: str) -> str:
    params = {
        "client_id": _get_client_id(),
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(ANTIGRAVITY_SCOPES),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{ANTIGRAVITY_AUTH_URL}?{urllib.parse.urlencode(params)}"




def _iso_expiry(expires_in: Optional[float]) -> str:
    ttl = float(expires_in) if expires_in else 3600.0
    epoch = time.time() + ttl
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(epoch)) + ".000000000Z"


def store_social_token(token: dict) -> str:
    access_token = token.get("access_token") or ""
    refresh_token = token.get("refresh_token") or ""
    email = token.get("email") or ""
    project_id = token.get("project_id") or ""

    if not refresh_token:
        raise AntigravityLoginError("Antigravity did not return a refresh token.")

    record = {
        "access_token": access_token,
        "expires_at": token.get("expires_at") or _iso_expiry(token.get("expires_in")),
        "refresh_token": refresh_token,
        "email": email,
        "project_id": project_id,
    }

    os.makedirs(_CREDENTIALS_DIR, exist_ok=True)
    try:
        with open(_CREDENTIALS_FILE, "w") as f:
            json.dump(record, f, indent=2)
        os.chmod(_CREDENTIALS_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as e:
        raise AntigravityLoginError(f"Could not write the Antigravity credential store: {e}") from e

    logger.info(f"Antigravity social token stored in {_CREDENTIALS_FILE} (email={email or 'unknown'}).")
    return _CREDENTIALS_FILE


def load_stored_refresh_token() -> str:
    if not os.path.isfile(_CREDENTIALS_FILE):
        return ""
    try:
        with open(_CREDENTIALS_FILE, "r") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("refresh_token") or "").strip()


def load_stored_account() -> dict:
    if not os.path.isfile(_CREDENTIALS_FILE):
        return {}
    try:
        with open(_CREDENTIALS_FILE, "r") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def clear_stored_credentials() -> bool:
    if not os.path.isfile(_CREDENTIALS_FILE):
        return False
    try:
        os.remove(_CREDENTIALS_FILE)
    except OSError as e:
        logger.error(f"Could not remove the Antigravity credential store: {e}")
        return False
    logger.info("Antigravity credentials cleared.")
    return True


def save_refresh_token_to_env(refresh_token: str, env_path: Optional[str] = None) -> str:
    if not env_path:
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

    lines: list[str] = []
    if os.path.isfile(env_path):
        with open(env_path, "r") as f:
            lines = f.read().splitlines()

    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith("ANTIGRAVITY_REFRESH_TOKEN="):
            lines[i] = f"ANTIGRAVITY_REFRESH_TOKEN={refresh_token}"
            replaced = True
            break
    if not replaced:
        lines.append(f"ANTIGRAVITY_REFRESH_TOKEN={refresh_token}")

    with open(env_path, "w") as f:
        f.write("\n".join(lines).rstrip() + "\n")

    os.environ["ANTIGRAVITY_REFRESH_TOKEN"] = refresh_token
    logger.info(f"ANTIGRAVITY_REFRESH_TOKEN written to {env_path}.")
    return env_path




class _CallbackResult:
    __slots__ = ("code", "state", "path", "error", "error_description")

    def __init__(self) -> None:
        self.code = ""
        self.state = ""
        self.path = ""
        self.error = ""
        self.error_description = ""


class AntigravityLoginSession:

    def __init__(self, port: Optional[int] = None) -> None:
        self.verifier, self.challenge = generate_pkce()
        self.state = _b64url(secrets.token_bytes(24))
        self.port = port or 0
        self.result = _CallbackResult()
        self.completed = asyncio.Event()
        self._server: Optional[asyncio.AbstractServer] = None
        self._servers: list[asyncio.AbstractServer] = []
        self.started_at = time.time()
        self.token: Optional[dict] = None
        self.exchange_error: str = ""

    @property
    def redirect_uri(self) -> str:
        return f"http://{ANTIGRAVITY_CALLBACK_HOST}:{self.port}{ANTIGRAVITY_CALLBACK_PATH}"

    @property
    def callback_uri(self) -> str:
        return self.redirect_uri

    async def start(self) -> str:
        await self._bind()
        logger.info(f"Antigravity sign-in listening on {ANTIGRAVITY_CALLBACK_HOST}:{self.port}.")
        auth_url = build_auth_url(
            state=self.state,
            code_challenge=self.challenge,
            redirect_uri=self.redirect_uri,
        )
        logger.info("Antigravity sign-in URL issued.")
        return auth_url

    async def _bind(self) -> None:
        candidates = (self.port,) if self.port else CALLBACK_PORT_CANDIDATES
        last_error: Optional[Exception] = None
        for port in candidates:
            bound = False
            for host in LOOPBACK_HOSTS:
                try:
                    server = await asyncio.start_server(
                        self._handle, host=host, port=port
                    )
                except OSError as e:
                    last_error = e
                    continue
                self._servers.append(server)
                bound = True
            if bound:
                self._server = self._servers[0]
                self.port = port
                return
        raise AntigravityLoginError(
            f"Could not bind a loopback port for the Antigravity callback: {last_error}"
        )

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=10)
            raw = request_line.decode("latin-1", "replace").strip()
            parts = raw.split(" ")
            target = parts[1] if len(parts) >= 2 else "/"

            parsed = urllib.parse.urlsplit(target)
            params = urllib.parse.parse_qs(parsed.query)
            self.result.path = parsed.path or "/"
            self.result.code = (params.get("code") or [""])[0]
            self.result.state = (params.get("state") or [""])[0]
            self.result.error = (params.get("error") or [""])[0]
            self.result.error_description = (params.get("error_description") or [""])[0]

            if self.result.error:
                body = _error_page(self.result.error_description or self.result.error)
                status = "400 Bad Request"
            elif self.result.state != self.state:
                body = _error_page("State mismatch. Start the sign-in again.")
                status = "400 Bad Request"
                self.result.error = "state_mismatch"
            elif not self.result.code:
                body = _error_page("Antigravity did not return an authorization code.")
                status = "400 Bad Request"
                self.result.error = "missing_code"
            else:
                body = _SUCCESS_PAGE
                status = "200 OK"

            payload = body.encode("utf-8")
            writer.write(
                f"HTTP/1.1 {status}\r\n"
                "Content-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "Connection: close\r\n\r\n".encode("latin-1")
                + payload
            )
            await writer.drain()
        except Exception as e:
            logger.error(f"Antigravity callback handler error: {e}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            self.completed.set()

    async def wait(self, timeout: float = LOGIN_TIMEOUT_SECONDS) -> _CallbackResult:
        try:
            await asyncio.wait_for(self.completed.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise AntigravityLoginError("Timed out waiting for the Antigravity sign-in to complete.")
        finally:
            await self.close()

        if self.result.error == "state_mismatch":
            raise AntigravityLoginError("Antigravity sign-in failed: state did not match (possible CSRF).")
        if self.result.error == "missing_code":
            raise AntigravityLoginError("Antigravity sign-in failed: no authorization code was returned.")
        if self.result.error:
            detail = self.result.error_description or self.result.error
            raise AntigravityLoginError(f"Antigravity sign-in failed: {detail}")
        return self.result

    async def close(self) -> None:
        for server in self._servers:
            try:
                server.close()
                await server.wait_closed()
            except Exception:
                pass
        self._servers = []
        self._server = None


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )




def _pick(source: dict, *keys: str) -> str:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def exchange_code(
    code: str,
    code_verifier: str,
    callback_uri: str,
) -> dict:
    if not code:
        raise AntigravityLoginError("Cannot exchange an empty authorization code.")

    payload = {
        "client_id": _get_client_id(),
        "client_secret": _get_client_secret(),
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": callback_uri,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(ANTIGRAVITY_TOKEN_URL, data=payload, headers=headers)
    except Exception as e:
        raise AntigravityLoginError(f"Antigravity token exchange request failed: {e}") from e

    if resp.status_code != 200:
        raise AntigravityLoginError(
            f"Antigravity token exchange failed with HTTP {resp.status_code}: {resp.text[:300]}"
        )

    try:
        data = resp.json()
    except Exception as e:
        raise AntigravityLoginError(f"Antigravity token exchange returned invalid JSON: {e}") from e

    if not isinstance(data, dict):
        raise AntigravityLoginError("Antigravity token exchange returned an unexpected payload.")

    access_token = _pick(data, "access_token", "accessToken")
    refresh_token = _pick(data, "refresh_token", "refreshToken")

    if not access_token:
        raise AntigravityLoginError("Antigravity token exchange did not return an access token.")
    if not refresh_token:
        raise AntigravityLoginError("Antigravity token exchange did not return a refresh token.")

    expires_in = None
    raw = data.get("expires_in")
    if raw is not None:
        try:
            expires_in = float(raw)
        except (TypeError, ValueError):
            expires_in = None

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "raw": data,
    }


def fetch_user_info(access_token: str) -> dict:
    if not access_token:
        return {}
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(ANTIGRAVITY_USERINFO_URL, headers=headers)
    except Exception:
        return {}
    if resp.status_code != 200:
        return {}
    try:
        data = resp.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}




async def run_login(
    port: Optional[int] = None,
    timeout: float = LOGIN_TIMEOUT_SECONDS,
    on_url=None,
    persist: bool = True,
) -> dict:
    session = AntigravityLoginSession(port=port)
    url = await session.start()
    if on_url:
        try:
            on_url(url)
        except Exception:
            pass

    result = await session.wait(timeout=timeout)
    token = exchange_code(
        code=result.code,
        code_verifier=session.verifier,
        callback_uri=session.callback_uri,
    )

    info = fetch_user_info(token["access_token"])
    token["email"] = _pick(info, "email")
    token["project_id"] = "aicode-consumers"

    if persist:
        token["credential_path"] = store_social_token(token)
        token["env_path"] = save_refresh_token_to_env(token["refresh_token"])

    return token
