"""Gemini Web (gemini.google.com) provider.

Calls Google Gemini's internal StreamGenerate endpoint using browser session
cookies — the same HTTP API the web frontend uses.

Auth: __Secure-1PSID + optional __Secure-1PSIDTS cookies, with an optional
      SAPISIDHASH Authorization header derived from the SAPISID cookie.
Discovery: GEMINI_WEB_COOKIE (full cookie string) or GEMINI_WEB_1PSID env
           vars, or automatic browser-profile extraction. The browser scan is
           dynamic: it walks the machine's actual installs (Brave / Chrome /
           Chromium / Edge / Vivaldi / Opera / Zen, every profile, native and
           Flatpak) plus Firefox, reading Chromium ``Cookies`` /
           ``Network/Cookies`` SQLite databases and Firefox ``cookies.sqlite``.
"""

import asyncio
import hashlib
import json
import os
import random
import re
import struct
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import httpx

from nim_router.logger import logger

# ─── Constants ───────────────────────────────────────────────────────────────

GEMINI_WEB_BASE = "https://gemini.google.com"
GEMINI_WEB_ORIGIN = "https://gemini.google.com"
GEMINI_WEB_STREAM_PATH = (
    "/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"
)
GEMINI_WEB_STREAM_PARAMS = "hl=en&rt=c"
# Fallback build label, used only when the live /app page cannot be parsed.
# Gemini still honours older boq_* labels, so this is a safety net rather
# than a load-bearing value — the real label is read from the page on every
# session because it rotates between deployments.
GEMINI_WEB_FALLBACK_BUILD_LABEL = "boq_assistant-bard-web-server_20240619.16_p0"
GEMINI_WEB_PREFIX = "gemini-web/"
GEMINI_WEB_DEFAULT_MODEL = "gemini-2.5-flash"

# Google's account service is the only stable way to tell a recognised
# __Secure-1PSID from a stale one: the Gemini frontend obfuscates (and rotates)
# every marker it used to expose.
GEMINI_WEB_ACCOUNT_PROBE_URL = "https://myaccount.google.com/"
_GEMINI_WEB_ACCOUNT_INTRO = "myaccount.google.com/intro"

GEMINI_WEB_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Environment variable names
_ENV_COOKIE = "GEMINI_WEB_COOKIE"
_ENV_1PSID = "GEMINI_WEB_1PSID"
_ENV_1PSIDTS = "GEMINI_WEB_1PSIDTS"
_ENV_SAPISID = "GEMINI_WEB_SAPISID"

# Maps our model IDs → StreamGenerate MODE_CATEGORY enum value (slot 79)
GEMINI_MODEL_CATEGORIES: dict[str, int] = {
    "gemini-3-pro": 70,
    "gemini-3-ultra": 71,
    "gemini-3-flash": 75,
    "gemini-2.5-pro": 53,
    "gemini-2.5-flash": 54,
    "gemini-2.5-flash-thinking": 55,
    "gemini-2.0-pro": 51,
    "gemini-2.0-flash": 52,
    "gemini-2.0-flash-thinking": 56,
}

# Browser profile discovery. We scan the machine's actual installs instead of a
# hardcoded list so non-Default profiles, Flatpak installs and Firefox are all
# covered. Only directories that belong to a known browser family are matched,
# which keeps Electron app stores (Code, etc.) out of the scan.
_BROWSER_DIR_MARKERS = (
    # Chromium family (Linux native)
    "BraveSoftware/Brave-Browser",
    "google-chrome",
    "chromium",
    "microsoft-edge",
    "vivaldi",
    "opera",
    "zen",
    # Chromium family (Flatpak)
    "com.brave.Browser",
    "com.google.Chrome",
    "org.chromium.Chromium",
    "com.microsoft.Edge",
    "com.vivaldi.Vivaldi",
    "com.opera.Opera",
    # Firefox family
    "firefox",
    "mozilla",
)

_CONFIG_ROOTS = (
    "~/.config",       # native installs
    "~/.var/app",      # Flatpak: ~/.var/app/<app-id>/config/...
)
_FIREFOX_ROOTS = (
    "~/.mozilla/firefox",
    "~/.var/app/org.mozilla.firefox/.mozilla/firefox",
    "~/snap/firefox/common/.mozilla/firefox",
)
_MAX_PROFILE_WALK_DEPTH = 6


def _looks_like_browser_profile(path: Path) -> bool:
    """True if `path` is a directory belonging to a known browser family."""
    lowered = str(path).lower()
    return any(marker.lower() in lowered for marker in _BROWSER_DIR_MARKERS)


def _profile_has_cookie_db(path: Path) -> bool:
    return (
        (path / "Cookies").is_file()
        or (path / "Network" / "Cookies").is_file()
        or (path / "cookies.sqlite").is_file()
    )


def _discover_browser_profiles() -> list[Path]:
    """Return browser profile directories that may hold Gemini cookies.

    Dynamic: walks the actual browser installs on this machine rather than a
    fixed list, so every profile (Default, Profile 1..N), Flatpak path and
    Firefox profile is considered. Electron/desktop-app cookie stores are
    excluded by matching only known browser directory names.
    """
    profiles: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path)
        if key not in seen and path.is_dir() and _profile_has_cookie_db(path):
            seen.add(key)
            profiles.append(path)

    for raw_root in _CONFIG_ROOTS:
        root = Path(raw_root).expanduser()
        if not root.is_dir():
            continue
        for dirpath, dirnames, _filenames in os.walk(root):
            depth = dirpath[len(str(root)):].count(os.sep)
            if depth >= _MAX_PROFILE_WALK_DEPTH:
                dirnames[:] = []
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d not in ("Cache", "Code Cache", "GPUCache")
            ]
            candidate = Path(dirpath)
            if _looks_like_browser_profile(candidate):
                add(candidate)

    for raw_root in _FIREFOX_ROOTS:
        root = Path(raw_root).expanduser()
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            if entry.is_dir() and (entry / "cookies.sqlite").is_file():
                add(entry)

    return profiles


# Cache for resolved credentials (TTL = 5 min)
_CRED_CACHE: dict[str, Any] = {"cookie": "", "sapisid": "", "source": "", "stamp": 0.0}
_CRED_TTL = 300.0

# ─── Pure-Python AES-128 CBC (for Linux Chrome v10/v11 cookie decryption) ────

_SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76"
    "ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d83115"
    "04c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f84"
    "53d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa8"
    "51a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d1973"
    "60814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479"
    "e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a"
    "703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df"
    "8ca1890dbfe6426841992d0fb054bb16"
)

_INV_SBOX = bytearray(256)
for _i, _v in enumerate(_SBOX):
    _INV_SBOX[_v] = _i


def _gmul(a: int, b: int) -> int:
    """GF(2^8) multiplication with AES polynomial 0x11b."""
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _aes128_key_schedule(key: bytes) -> list[list[int]]:
    """Expand a 16-byte AES key into 11 round keys (each 16 bytes flat)."""
    w = [list(key[i * 4: (i + 1) * 4]) for i in range(4)]
    rcon = 0x01
    for i in range(4, 44):
        temp = list(w[i - 1])
        if i % 4 == 0:
            temp = temp[1:] + temp[:1]  # RotWord
            temp = [_SBOX[b] for b in temp]  # SubWord
            temp[0] ^= rcon
            rcon = ((rcon << 1) ^ 0x1B) & 0xFF if rcon & 0x80 else (rcon << 1) & 0xFF
        w.append([w[i - 4][j] ^ temp[j] for j in range(4)])
    round_keys: list[list[int]] = []
    for r in range(11):
        rk: list[int] = []
        for c in range(4):
            rk.extend(w[r * 4 + c])
        round_keys.append(rk)
    return round_keys


def _aes128_decrypt_block(block: bytes, round_keys: list[list[int]]) -> list[int]:
    """AES-128 inverse cipher (FIPS-197 §5.3) — state indexed as row + 4*col."""
    state = list(block)

    def add_round_key(rk: list[int]) -> None:
        for idx in range(16):
            state[idx] ^= rk[idx]

    def inv_sub_bytes() -> None:
        for idx in range(16):
            state[idx] = _INV_SBOX[state[idx]]

    def inv_shift_rows() -> None:
        for row in range(1, 4):
            orig = [state[row + 4 * c] for c in range(4)]
            for c in range(4):
                state[row + 4 * c] = orig[(c - row) % 4]

    def inv_mix_columns() -> None:
        M = [
            [0x0E, 0x0B, 0x0D, 0x09],
            [0x09, 0x0E, 0x0B, 0x0D],
            [0x0D, 0x09, 0x0E, 0x0B],
            [0x0B, 0x0D, 0x09, 0x0E],
        ]
        for c in range(4):
            s = [state[r + 4 * c] for r in range(4)]
            for r in range(4):
                state[r + 4 * c] = (
                    _gmul(M[r][0], s[0])
                    ^ _gmul(M[r][1], s[1])
                    ^ _gmul(M[r][2], s[2])
                    ^ _gmul(M[r][3], s[3])
                )

    add_round_key(round_keys[10])
    for rnd in range(9, 0, -1):
        inv_shift_rows()
        inv_sub_bytes()
        add_round_key(round_keys[rnd])
        inv_mix_columns()
    inv_shift_rows()
    inv_sub_bytes()
    add_round_key(round_keys[0])
    return state


def _aes128_cbc_decrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """Decrypt AES-128-CBC; silently drops trailing partial block."""
    rks = _aes128_key_schedule(key)
    out = bytearray()
    prev = iv
    n = (len(data) // 16) * 16
    for off in range(0, n, 16):
        block = data[off: off + 16]
        dec = _aes128_decrypt_block(block, rks)
        out.extend(bytes(dec[i] ^ prev[i] for i in range(16)))
        prev = block
    return bytes(out)


def _linux_aes_key() -> bytes:
    """Derive the AES key used by Chrome/Brave/Chromium on Linux."""
    return hashlib.pbkdf2_hmac("sha1", b"peanuts", b"saltysalt", 1, dklen=16)


def _decrypt_chrome_cookie(raw: bytes) -> str:
    """Decrypt a Chrome cookie blob (v10/v11 on Linux, plaintext fallback)."""
    if raw[:3] in (b"v10", b"v11"):
        try:
            plain = _aes128_cbc_decrypt(raw[3:], _linux_aes_key(), b" " * 16)
        except Exception:
            return ""
        # PKCS7 unpad
        if plain:
            pad = plain[-1]
            if 1 <= pad <= 16 and plain.endswith(bytes([pad]) * pad):
                plain = plain[:-pad]
        text = plain.decode("utf-8", "ignore")
        # Cookie values are ASCII; anything else means the wrong key was used.
        if any(ord(ch) > 0x7E for ch in text):
            return ""
        return text
    if raw[:3] == b"v20":
        return ""  # app-bound encryption, not supported without OS integration
    return raw.decode("utf-8", "ignore")

# ─── Cookie helpers ───────────────────────────────────────────────────────────

def _extract_cookie_value(cookie: str, name: str) -> str:
    """Extract value for `name` from a semicolon-separated cookie string."""
    for part in (cookie or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k.strip() == name:
            return v.strip()
    return ""


def _normalize_cookie(raw: str, name: str = "__Secure-1PSID") -> str:
    """Return a `name=value` pair, or the raw string if it already contains '='."""
    trimmed = (raw or "").strip()
    if not trimmed:
        return ""
    return trimmed if "=" in trimmed else f"{name}={trimmed}"


def _build_cookie_string(psid: str, psidts: str = "", extra: str = "") -> str:
    """Combine cookie parts into a single header value."""
    parts: list[str] = []
    if psid:
        parts.append(_normalize_cookie(psid, "__Secure-1PSID"))
    if psidts:
        parts.append(_normalize_cookie(psidts, "__Secure-1PSIDTS"))
    if extra and extra not in parts:
        parts.append(extra)
    return "; ".join(parts)


def _non_ascii_position(value: str) -> Optional[tuple[int, str]]:
    """Return (index, char) of the first non-ASCII character, or None."""
    for idx, ch in enumerate(value or ""):
        if ord(ch) > 0x7E:
            return idx, ch
    return None


def _ascii_safe_header(value: str) -> str:
    """Drop characters that HTTP header values cannot carry.

    Header values must be ASCII (httpx encodes them with ``value.encode("ascii")``).
    Cookie values are ASCII by spec, so a non-ASCII character means the value was
    corrupted — a bad paste or a failed browser-cookie decrypt — and would
    otherwise make httpx raise a bare ``UnicodeEncodeError``.
    """
    return "".join(ch for ch in (value or "") if 0x20 <= ord(ch) < 0x7F)

# ─── SAPISIDHASH ─────────────────────────────────────────────────────────────

def compute_sapisid_hash(sapisid: str, origin: str = GEMINI_WEB_ORIGIN) -> str:
    """Return the Authorization header value: SAPISIDHASH {epoch}_{sha1}."""
    epoch = int(time.time())
    digest = hashlib.sha1(f"{epoch} {sapisid} {origin}".encode()).hexdigest()
    return f"SAPISIDHASH {epoch}_{digest}"

# ─── Browser credential extraction ───────────────────────────────────────────

def _scan_gemini_cookies(profile: Path) -> dict[str, str]:
    """Read __Secure-1PSID / __Secure-1PSIDTS / SAPISID from a browser profile.

    Supports Chromium-family databases (legacy ``Cookies`` and Chrome 127+
    ``Network/Cookies`` with AES-CBC v10/v11 decryption on Linux) and Firefox
    plaintext ``cookies.sqlite``.
    """
    found: dict[str, str] = {}
    target_names = {"__Secure-1PSID", "__Secure-1PSIDTS", "SAPISID", "__Secure-3PAPISID"}

    def scan_chromium(db_path: Path) -> bool:
        if not db_path.is_file():
            return False
        try:
            import sqlite3
            uri = f"file:{db_path}?mode=ro&immutable=1"
            conn = sqlite3.connect(uri, uri=True, timeout=5.0)
            try:
                rows = conn.execute(
                    "SELECT name, value, encrypted_value FROM cookies "
                    "WHERE host_key LIKE '%.google.com%'"
                ).fetchall()
            finally:
                conn.close()
        except Exception:
            return False

        for name, value, enc in rows:
            if name not in target_names or found.get(name):
                continue
            if value:
                found[name] = value
            elif enc:
                decrypted = _decrypt_chrome_cookie(bytes(enc))
                if decrypted:
                    found[name] = decrypted
                elif name == "__Secure-1PSID":
                    logger.debug(
                        "Gemini Web: __Secure-1PSID in %s uses app-bound "
                        "encryption (v11/v20) and cannot be decrypted without "
                        "OS keyring access; paste the cookie in the dashboard "
                        "or set GEMINI_WEB_1PSID.",
                        db_path,
                    )
        return bool(found.get("__Secure-1PSID"))

    if scan_chromium(profile / "Cookies"):
        return found
    if scan_chromium(profile / "Network" / "Cookies"):
        return found

    # Firefox keeps cookie values in plaintext.
    ff_db = profile / "cookies.sqlite"
    if ff_db.is_file():
        try:
            import sqlite3
            uri = f"file:{ff_db}?mode=ro&immutable=1"
            conn = sqlite3.connect(uri, uri=True, timeout=5.0)
            try:
                rows = conn.execute(
                    "SELECT name, value FROM moz_cookies "
                    "WHERE host LIKE '%.google.com%'"
                ).fetchall()
            finally:
                conn.close()
            for name, value in rows:
                if name in target_names and value and not found.get(name):
                    found[name] = value
        except Exception:
            pass

    return found


def extract_browser_credentials() -> dict[str, str]:
    """Scan local browser profiles for gemini.google.com session cookies.

    Returns a dict with the individual cookie names plus a combined
    ``cookie`` header value and the profile ``source`` path.
    """
    profiles = _discover_browser_profiles()
    for profile in profiles:
        creds = _scan_gemini_cookies(profile)
        psid = creds.get("__Secure-1PSID", "")
        if not psid:
            continue
        creds["cookie"] = _build_cookie_string(psid, creds.get("__Secure-1PSIDTS", ""))
        creds["source"] = str(profile)
        return creds

    if profiles:
        logger.debug(
            "Gemini Web: scanned %d browser profile(s) but none contained a "
            "gemini.google.com session cookie (__Secure-1PSID).",
            len(profiles),
        )
    else:
        logger.debug(
            "Gemini Web: no browser cookie database was found on this machine. "
            "Set GEMINI_WEB_COOKIE / GEMINI_WEB_1PSID instead."
        )
    return {}


def resolve_credentials(force: bool = False) -> dict[str, str]:
    """Return {'cookie': '...', 'sapisid': '...', 'source': '...'}.

    Resolution order:
      1. GEMINI_WEB_COOKIE env var (full cookie string or bare 1PSID value)
      2. GEMINI_WEB_1PSID + optional GEMINI_WEB_1PSIDTS env vars
      3. Dynamic browser profile scan (all detected Chromium-family and
         Firefox profiles, native and Flatpak)

    Results are cached for 5 minutes.
    """
    now = time.time()
    if not force and _CRED_CACHE["cookie"] and (now - _CRED_CACHE["stamp"]) < _CRED_TTL:
        return {"cookie": _CRED_CACHE["cookie"], "sapisid": _CRED_CACHE["sapisid"], "source": _CRED_CACHE["source"]}

    cookie = ""
    sapisid = ""
    source = ""

    env_cookie = os.environ.get(_ENV_COOKIE, "").strip()
    env_1psid = os.environ.get(_ENV_1PSID, "").strip()
    env_1psidts = os.environ.get(_ENV_1PSIDTS, "").strip()
    env_sapisid = os.environ.get(_ENV_SAPISID, "").strip()

    if env_cookie:
        cookie = _normalize_cookie(env_cookie)
        source = "env"
    elif env_1psid:
        cookie = _build_cookie_string(env_1psid, env_1psidts)
        source = "env"

    if not cookie:
        browser = extract_browser_credentials()
        psid = browser.get("__Secure-1PSID", "")
        psidts = browser.get("__Secure-1PSIDTS", "")
        if psid:
            cookie = _build_cookie_string(psid, psidts)
            source = browser.get("source", "browser")
            # Prefer browser SAPISID for the hash if not set via env
            if not env_sapisid:
                env_sapisid = (
                    browser.get("SAPISID")
                    or browser.get("__Secure-3PAPISID")
                    or ""
                )

    if env_sapisid:
        sapisid = env_sapisid
    elif cookie:
        sapisid = (
            _extract_cookie_value(cookie, "SAPISID")
            or _extract_cookie_value(cookie, "__Secure-3PAPISID")
        )

    bad = _non_ascii_position(cookie)
    if bad is not None:
        idx, ch = bad
        logger.warning(
            f"Gemini Web cookie contains a non-ASCII character "
            f"(U+{ord(ch):04X} at position {idx}); dropping invalid characters. "
            f"Re-copy the cookie from the browser if authentication fails."
        )
        cookie = _ascii_safe_header(cookie)

    _CRED_CACHE.update({"cookie": cookie, "sapisid": sapisid, "source": source, "stamp": now})
    return {"cookie": cookie, "sapisid": sapisid, "source": source}

# ─── Error types ─────────────────────────────────────────────────────────────

class GeminiWebError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class GeminiWebAuthError(GeminiWebError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=401)


class GeminiWebUpstreamError(GeminiWebError):
    pass

# ─── Model ID helpers ─────────────────────────────────────────────────────────

def gemini_web_upstream_model_id(model_id: str) -> str:
    """Strip provider prefix and return the bare model slug."""
    mid = (model_id or "").strip()
    for prefix in ("[Gemini Web] ", "[gemini web] "):
        if mid.startswith(prefix):
            mid = mid[len(prefix):].strip()
    if mid.lower().startswith(GEMINI_WEB_PREFIX):
        mid = mid[len(GEMINI_WEB_PREFIX):]
    return mid.strip() or GEMINI_WEB_DEFAULT_MODEL


def gemini_web_model_category(model_id: str) -> int:
    """Return the MODE_CATEGORY integer for StreamGenerate slot 79."""
    slug = gemini_web_upstream_model_id(model_id)
    return GEMINI_MODEL_CATEGORIES.get(slug, GEMINI_MODEL_CATEGORIES[GEMINI_WEB_DEFAULT_MODEL])

# ─── StreamGenerate payload builders ─────────────────────────────────────────

def _flatten_messages(messages: list[dict]) -> str:
    """Collapse a multi-turn message list into a single prompt string."""
    parts: list[str] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "user").lower()
        content = msg.get("content")
        if isinstance(content, list):
            # vision-style content blocks → extract text pieces
            content = " ".join(
                str(b.get("text") or "")
                for b in content
                if isinstance(b, dict) and isinstance(b.get("text"), str)
            ).strip()
        text = str(content or "").strip()
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


def _build_inner_array(prompt: str, model_category: int) -> list:
    """Construct the 80-slot inner array for StreamGenerate f.req."""
    inner: list = [None] * 80
    inner[0] = [prompt, 0, None, None, None, None, 0]
    inner[1] = ["en"]
    inner[2] = ["", "", "", None, None, None, None, None, None, ""]
    inner[6] = [0]
    inner[7] = 1
    inner[10] = 1
    inner[11] = 0
    inner[17] = [[0]]
    inner[18] = 0
    inner[27] = 1
    inner[30] = [4]
    inner[41] = [2]
    inner[53] = 0
    inner[59] = str(uuid.uuid4())
    inner[61] = []
    inner[68] = 1
    inner[79] = model_category
    return inner

# ─── Response parsing ─────────────────────────────────────────────────────────

def _parse_line_text(line: str) -> str:
    """Extract the text carried by a single StreamGenerate response line.

    Gemini repeats the *whole* answer in every text frame, so the value
    returned here is cumulative — callers must diff it against the previous
    frame (see :func:`_text_delta`) to recover true streaming deltas.
    """
    line = line.strip()
    if not line or line == ")]}'":
        return ""
    if line.isdigit():
        return ""
    if "wrb.fr" not in line:
        return ""
    try:
        arr = json.loads(line)
    except (TypeError, ValueError):
        return ""
    if not isinstance(arr, list):
        return ""
    text_chunks: list[str] = []
    for item in arr:
        if not isinstance(item, list) or not item:
            continue
        # Each item is [event_name, session, payload_json, ...]
        if item[0] != "wrb.fr":
            continue
        payload_str = item[2] if len(item) > 2 else None
        if not isinstance(payload_str, str):
            continue
        try:
            inner = json.loads(payload_str)
        except (TypeError, ValueError):
            continue
        # Navigate inner[4][0][1] — the text chunk array. The payload is
        # sometimes a list and sometimes a dict, so guard both.
        try:
            text_array = inner[4][0][1]
        except (IndexError, TypeError, KeyError):
            continue
        if not isinstance(text_array, list):
            continue
        for piece in text_array:
            if isinstance(piece, str):
                text_chunks.append(piece)
    return "".join(text_chunks)


def _text_delta(cumulative: str, seen: str) -> tuple[str, str]:
    """Diff a cumulative text frame against what has already been emitted.

    Returns ``(delta, new_seen)``. Gemini re-sends the entire answer in every
    text frame, so concatenating frames verbatim repeats the answer several
    times over; only the suffix beyond ``seen`` is new.
    """
    if not cumulative:
        return "", seen
    if cumulative.startswith(seen):
        return cumulative[len(seen):], cumulative
    if seen.startswith(cumulative):
        # A stale frame that repeats what we already emitted.
        return "", seen
    # Divergent frame (server rewrote the answer) — take it as-is.
    return cumulative, cumulative


def parse_stream_response(raw: str) -> str:
    """Parse a full StreamGenerate response body and return the full answer text."""
    chunks: list[str] = []
    seen = ""
    for line in (raw or "").split("\n"):
        cumulative = _parse_line_text(line)
        if not cumulative:
            continue
        delta, seen = _text_delta(cumulative, seen)
        if delta:
            chunks.append(delta)
    return "".join(chunks)

# ─── SSE helpers ─────────────────────────────────────────────────────────────

def _chunk_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")


def _make_delta_chunk(
    completion_id: str,
    created: int,
    model_label: str,
    content: str,
    finish_reason: Optional[str] = None,
) -> bytes:
    return _sse({
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_label,
        "choices": [
            {
                "index": 0,
                "delta": ({"content": content} if content else {}),
                "finish_reason": finish_reason,
            }
        ],
    })

# ─── HTTP request builder ─────────────────────────────────────────────────────

def _build_request_headers(cookie: str, sapisid: str) -> dict[str, str]:
    headers: dict[str, str] = {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": _ascii_safe_header(cookie),
        "Origin": GEMINI_WEB_ORIGIN,
        "Referer": f"{GEMINI_WEB_ORIGIN}/",
        "User-Agent": GEMINI_WEB_USER_AGENT,
        "X-Same-Domain": "1",
    }
    if sapisid:
        headers["Authorization"] = compute_sapisid_hash(sapisid)
    return headers


def _build_stream_url(build_label: str = "") -> str:
    """Build the StreamGenerate URL.

    ``bl`` is the frontend build label. It rotates between deployments, so it
    is read from the live /app page; the hardcoded value is only a fallback.
    """
    req_id = random.randint(100000, 999999)
    label = (build_label or "").strip() or GEMINI_WEB_FALLBACK_BUILD_LABEL
    return (
        f"{GEMINI_WEB_BASE}{GEMINI_WEB_STREAM_PATH}"
        f"?bl={label}&{GEMINI_WEB_STREAM_PARAMS}&_reqid={req_id}"
    )


def _build_form_body(
    prompt: str, model_category: int, at_token: str = ""
) -> dict[str, str]:
    inner = _build_inner_array(prompt, model_category)
    # ensure_ascii=True keeps the request body pure ASCII; non-ASCII prompts
    # (e.g. CJK) become \\uXXXX escapes and are decoded by the server's JSON parser.
    freq = json.dumps([None, json.dumps(inner, ensure_ascii=True)], ensure_ascii=True)
    body = {"f.req": freq}
    # The web frontend sends the page's CSRF token as `at`. Current builds
    # ship it under an obfuscated key and may omit it altogether — the
    # endpoint still answers without it, so it is best-effort.
    if at_token:
        body["at"] = at_token
    return body

# ─── Session / auth helpers ───────────────────────────────────────────────────

# The Gemini frontend used to embed a signed-in marker on every /app page (the
# "SNlM0e" CSRF token) and StreamGenerate required it as the `at` form field.
# That token no longer exists in current builds — the key is obfuscated and
# rotates — so it can no longer be used to tell a signed-in page from a
# signed-out one. Everything below therefore matches on the *shape* of values
# rather than on a key name, and the signed-in check itself is delegated to
# Google's account service.

_WIZ_GLOBAL_DATA_RE = re.compile(r"window\.WIZ_global_data\s*=\s*\{")
_LEGACY_AT_TOKEN_RE = re.compile(r'"SNlM0e":"([^"]+)"')
_BUILD_LABEL_RE = re.compile(r"^boq_[\w.-]+_p\d+$")
_BUILD_LABEL_BODY_RE = re.compile(r"boq_[A-Za-z0-9_.-]+_p\d+")
_CAMS_PREFIX = "CAMS"

# Page-derived data (build label + CSRF token) is cached briefly: the build
# label rotates between deployments and the token is tied to a page load.
_SESSION_TTL = 300.0
_SESSION_CACHE: dict[str, Any] = {"cookie": "", "at": "", "bl": "", "stamp": 0.0}

# Credential verdicts are cached per cookie so a stream does not pay for a
# probe on every request.
_PROBE_TTL = 300.0
_PROBE_CACHE: dict[str, Any] = {"cookie": "", "ok": None, "stamp": 0.0}


def _extract_json_object(text: str, start: int) -> str:
    """Return the JSON object starting at ``text[start]`` (brace-balanced)."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return ""


def _parse_wiz_global_data(body: str) -> dict:
    """Return the parsed ``window.WIZ_global_data`` object from an /app page."""
    body = body or ""
    match = _WIZ_GLOBAL_DATA_RE.search(body)
    if not match:
        return {}
    raw = _extract_json_object(body, match.end() - 1)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _extract_build_label(body: str) -> str:
    """Return the frontend build label (``boq_*_pN``) from an /app page.

    The label lives in ``WIZ_global_data`` under an obfuscated key that
    rotates between builds, so it is located by value shape.
    """
    for value in _parse_wiz_global_data(body).values():
        if isinstance(value, str) and _BUILD_LABEL_RE.match(value):
            return value
    match = _BUILD_LABEL_BODY_RE.search(body or "")
    return match.group(0) if match else ""


def _extract_at_token(body: str) -> str:
    """Return the page's CSRF (``at``) token, or '' when there is none.

    Older builds exposed it as ``SNlM0e``; current builds keep the same
    ``CAMS...`` value shape but under a rotating, obfuscated key — so the
    value is matched by shape rather than by key name.
    """
    match = _LEGACY_AT_TOKEN_RE.search(body or "")
    if match:
        return match.group(1)
    data = _parse_wiz_global_data(body)
    for value in data.values():
        if isinstance(value, str) and value.startswith(_CAMS_PREFIX):
            return value
    for value in data.values():
        if isinstance(value, str) and '"token"' in value:
            try:
                token = json.loads(value).get("token")
            except (TypeError, ValueError, AttributeError):
                continue
            if isinstance(token, str) and token.startswith(_CAMS_PREFIX):
                return token
    return ""


def _invalidate_session() -> None:
    """Drop cached page-derived session data and the credential verdict."""
    _SESSION_CACHE.update({"cookie": "", "at": "", "bl": "", "stamp": 0.0})
    _PROBE_CACHE.update({"cookie": "", "ok": None, "stamp": 0.0})


# Backwards-compatible alias: older call sites invalidate the cached token.
_invalidate_at_token = _invalidate_session


def _response_looks_like_auth_redirect(body: str, final_url: str) -> bool:
    """True when the upstream answered with a Google sign-in page."""
    if "accounts.google.com" in (final_url or ""):
        return True
    lowered = (body or "").lower()
    return "accounts.google.com/signin" in lowered or "service-login" in lowered


async def _get_session(
    cookie: str, client: Optional[httpx.AsyncClient] = None
) -> dict[str, str]:
    """Fetch /app and return the page-derived ``at`` token and ``bl`` label.

    Both are best-effort: the CSRF token may be absent entirely and the build
    label may be unparseable, in which case the caller falls back to a
    known-good label.
    """
    now = time.time()
    if (
        _SESSION_CACHE["cookie"] == cookie
        and _SESSION_CACHE["stamp"]
        and (now - _SESSION_CACHE["stamp"]) < _SESSION_TTL
    ):
        return {"at": _SESSION_CACHE["at"], "bl": _SESSION_CACHE["bl"]}

    url = f"{GEMINI_WEB_BASE}/app"
    headers = {
        "Cookie": _ascii_safe_header(cookie),
        "User-Agent": GEMINI_WEB_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        if client is not None:
            resp = await client.get(
                url, headers=headers, follow_redirects=True, timeout=15.0
            )
        else:
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True, max_redirects=3
            ) as own:
                resp = await own.get(url, headers=headers)
    except UnicodeEncodeError as exc:
        raise GeminiWebAuthError(
            "Gemini Web cookie contains characters that cannot be sent in an HTTP "
            "header. Re-copy the __Secure-1PSID cookie from the browser."
        ) from exc
    except httpx.RequestError as exc:
        raise GeminiWebUpstreamError(f"Gemini Web network error: {exc}") from exc

    body = resp.text or ""
    session = {"at": _extract_at_token(body), "bl": _extract_build_label(body)}
    _SESSION_CACHE.update(
        {"cookie": cookie, "at": session["at"], "bl": session["bl"], "stamp": now}
    )
    return session


async def _probe_credentials(
    cookie: str, client: Optional[httpx.AsyncClient] = None
) -> bool:
    """Return True when Google recognises ``cookie`` as a signed-in session.

    The Gemini frontend exposes no stable signed-in marker any more, so the
    cookie is validated against Google's account service instead. A
    recognised session is bounced to ``accounts.google.com/ServiceLogin``
    with ``passive=`` (Google wants to complete the session silently); an
    unrecognised cookie lands on ``myaccount.google.com/intro``.

    The request always carries an explicit ``Cookie`` header so that a
    client's cookie jar cannot leak a previous session into the verdict.
    """
    now = time.time()
    if (
        _PROBE_CACHE["cookie"] == cookie
        and _PROBE_CACHE["ok"] is not None
        and (now - _PROBE_CACHE["stamp"]) < _PROBE_TTL
    ):
        return bool(_PROBE_CACHE["ok"])

    headers = {
        "Cookie": _ascii_safe_header(cookie),
        "User-Agent": GEMINI_WEB_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        if client is not None:
            resp = await client.get(
                GEMINI_WEB_ACCOUNT_PROBE_URL,
                headers=headers,
                follow_redirects=False,
                timeout=15.0,
            )
        else:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as own:
                resp = await own.get(GEMINI_WEB_ACCOUNT_PROBE_URL, headers=headers)
    except UnicodeEncodeError as exc:
        raise GeminiWebAuthError(
            "Gemini Web cookie contains characters that cannot be sent in an HTTP "
            "header. Re-copy the __Secure-1PSID cookie from the browser."
        ) from exc
    except httpx.RequestError as exc:
        raise GeminiWebUpstreamError(f"Gemini Web network error: {exc}") from exc

    location = resp.headers.get("location", "") or ""
    ok = _GEMINI_WEB_ACCOUNT_INTRO not in location
    _PROBE_CACHE.update({"cookie": cookie, "ok": ok, "stamp": now})
    return ok


async def _ensure_valid_session(
    cookie: str,
    client: Optional[httpx.AsyncClient] = None,
    *,
    strict: bool = True,
) -> None:
    """Raise :class:`GeminiWebAuthError` when the cookie is not recognised.

    With ``strict=False`` a probe that cannot be completed (network trouble)
    is downgraded to a warning instead of failing the request.
    """
    try:
        ok = await _probe_credentials(cookie, client)
    except GeminiWebUpstreamError:
        if strict:
            raise
        logger.warning(
            "Gemini Web credential probe failed; continuing without a verdict."
        )
        return
    if ok:
        return
    _invalidate_session()
    raise GeminiWebAuthError(
        "Gemini Web credentials are invalid or expired: Google does not recognise "
        "the __Secure-1PSID cookie. Copy a fresh __Secure-1PSID (and optionally "
        "__Secure-1PSIDTS and SAPISID) from a browser signed in to gemini.google.com "
        "and update GEMINI_WEB_COOKIE."
    )

# ─── list_models ─────────────────────────────────────────────────────────────

async def list_models() -> list[dict]:
    """Verify credentials and return the static Gemini Web model catalog."""
    creds = resolve_credentials()
    if not creds["cookie"]:
        raise GeminiWebAuthError(
            "Gemini Web is not configured. Set GEMINI_WEB_COOKIE or GEMINI_WEB_1PSID, "
            "or sign in to gemini.google.com in a local browser."
        )

    # The Gemini frontend no longer exposes a usable signed-in marker on its
    # own pages, so the cookie is validated against Google's account service.
    await _ensure_valid_session(creds["cookie"], None, strict=True)
    # Warm the page-derived session (build label / CSRF token) for the first
    # real request; a failure here is an upstream, not a credential, problem.
    await _get_session(creds["cookie"], None)

    return [
        {
            "id": f"{GEMINI_WEB_PREFIX}{slug}",
            "provider": "Gemini Web",
            "description": f"Gemini Web — {slug}",
            "supports_image": False,
        }
        for slug in GEMINI_MODEL_CATEGORIES
    ]

# ─── stream_chat_completion ───────────────────────────────────────────────────

async def stream_chat_completion(
    model_id: str,
    messages: list[dict],
    client: httpx.AsyncClient,
    tools: Optional[list[dict]] = None,
    tool_choice: Any = None,
) -> AsyncGenerator[bytes, None]:
    """Yield SSE bytes for a Gemini Web chat completion (streaming)."""
    creds = resolve_credentials()
    cookie = creds["cookie"]
    if not cookie:
        raise GeminiWebAuthError(
            "Gemini Web is not configured. Set GEMINI_WEB_COOKIE or GEMINI_WEB_1PSID."
        )

    prompt = _flatten_messages(messages)
    if not prompt.strip():
        raise GeminiWebUpstreamError("Gemini Web: empty prompt after flattening messages")

    category = gemini_web_model_category(model_id)
    slug = gemini_web_upstream_model_id(model_id)
    model_label = f"{GEMINI_WEB_PREFIX}{slug}"
    completion_id = _chunk_id()
    created = int(time.time())

    # Fail fast on a cookie Google no longer recognises. A strict probe would
    # turn a transient network blip into a hard failure, so streaming downgrades
    # that case to a warning and lets the real request decide.
    await _ensure_valid_session(cookie, client, strict=False)

    session = await _get_session(cookie, client)
    url = _build_stream_url(session["bl"])
    headers = _build_request_headers(cookie, creds.get("sapisid", ""))
    form = _build_form_body(prompt, category, session["at"])

    # Open the streaming request
    try:
        request = client.build_request("POST", url, headers=headers, data=form)
        response = await client.send(request, stream=True)
    except UnicodeEncodeError as exc:
        raise GeminiWebAuthError(
            "Gemini Web cookie contains characters that cannot be sent in an HTTP "
            "header. Re-copy the __Secure-1PSID cookie from the browser."
        ) from exc
    except httpx.RequestError as exc:
        raise GeminiWebUpstreamError(f"Gemini Web network error: {exc}") from exc

    # Auth check on the response headers
    if response.status_code in (401, 403):
        await response.aclose()
        _invalidate_session()
        raise GeminiWebAuthError(
            f"Gemini Web authentication failed (HTTP {response.status_code}). "
            "Re-extract cookies from a signed-in browser."
        )
    if response.status_code != 200:
        body_preview = (await response.aread()).decode("utf-8", "ignore")[:200]
        await response.aclose()
        raise GeminiWebUpstreamError(
            f"Gemini Web returned HTTP {response.status_code}: {body_preview}"
        )

    # Collect body text — we need to detect auth redirects from HTML responses
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        body = (await response.aread()).decode("utf-8", "ignore")
        await response.aclose()
        if _response_looks_like_auth_redirect(body, str(response.url)):
            _invalidate_session()
            raise GeminiWebAuthError(
                "Gemini Web session expired. Re-extract cookies from a signed-in browser."
            )
        raise GeminiWebUpstreamError("Gemini Web returned an unexpected HTML response.")

    async def _generator() -> AsyncGenerator[bytes, None]:
        emitted_any = False
        seen = ""
        try:
            async for line in response.aiter_lines():
                cumulative = _parse_line_text(line)
                if not cumulative:
                    continue
                # Gemini re-sends the whole answer in every text frame; only
                # the suffix beyond what we already emitted is new.
                delta, seen = _text_delta(cumulative, seen)
                if not delta:
                    continue
                emitted_any = True
                yield _make_delta_chunk(completion_id, created, model_label, delta)

            if not emitted_any:
                raise GeminiWebUpstreamError(
                    "Gemini Web returned no text. "
                    "The model may have refused the request or the cookies are expired."
                )

            yield _make_delta_chunk(completion_id, created, model_label, "", finish_reason="stop")
            yield b"data: [DONE]\n\n"
        except GeminiWebError:
            raise
        except Exception as exc:
            raise GeminiWebUpstreamError(f"Gemini Web stream error: {exc}") from exc
        finally:
            await response.aclose()

    async for chunk in _generator():
        yield chunk

# ─── create_chat_completion ───────────────────────────────────────────────────

async def create_chat_completion(
    model_id: str,
    messages: list[dict],
    client: httpx.AsyncClient,
    tools: Optional[list[dict]] = None,
    tool_choice: Any = None,
) -> dict:
    """Non-streaming completion — aggregates the streaming response."""
    text_parts: list[str] = []

    async for chunk in stream_chat_completion(model_id, messages, client):
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
                text_parts.append(delta["content"])

    full_text = "".join(text_parts)
    slug = gemini_web_upstream_model_id(model_id)
    model_label = f"{GEMINI_WEB_PREFIX}{slug}"
    return {
        "id": _chunk_id(),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_label,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": full_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
