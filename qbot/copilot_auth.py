"""GitHub Copilot API authentication via OAuth device flow.

Flow:
1. User initiates OAuth device flow → gets a user_code to enter at github.com/login/device
2. App polls until user authorizes → receives an OAuth access token
3. OAuth token is exchanged for a short-lived Copilot session token (~30 min)
4. Copilot token is used as Bearer auth against api.githubcopilot.com

Tokens are cached to disk so the user doesn't have to re-authorize every time.
"""

import json
import os
import time
import threading
import requests

SETTINGS_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "QBot")
TOKEN_FILE = os.path.join(SETTINGS_DIR, "copilot_token.json")

# GitHub Copilot's public OAuth App client ID (same one used by copilot.vim / VS Code)
CLIENT_ID = "Iv1.b507a08c87ecfe98"

COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
COPILOT_API_BASE = "https://api.githubcopilot.com"

_lock = threading.Lock()
_cached_oauth_token: str | None = None
_cached_copilot_token: str | None = None
_copilot_token_expires: float = 0


def _load_cached_oauth() -> str | None:
    """Load saved OAuth token from disk."""
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("oauth_token")
    except (json.JSONDecodeError, OSError):
        return None


def _save_oauth(token: str):
    """Persist OAuth token to disk."""
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump({"oauth_token": token}, f)


def _clear_cached():
    """Remove cached tokens."""
    global _cached_oauth_token, _cached_copilot_token, _copilot_token_expires
    _cached_oauth_token = None
    _cached_copilot_token = None
    _copilot_token_expires = 0
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)


def start_device_flow() -> dict:
    """Start the OAuth device flow. Returns dict with user_code, verification_uri, device_code, interval."""
    r = requests.post(
        "https://github.com/login/device/code",
        headers={"Accept": "application/json"},
        json={"client_id": CLIENT_ID, "scope": "copilot"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def poll_for_token(device_code: str, interval: int = 5, timeout: int = 300) -> str:
    """Poll GitHub until the user authorizes the device. Returns OAuth access token.

    Raises TimeoutError if user doesn't authorize within timeout seconds.
    Raises RuntimeError on auth errors (denied, expired, etc).
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(interval)
        r = requests.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            json={
                "client_id": CLIENT_ID,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=15,
        )
        data = r.json()
        if "access_token" in data:
            token = data["access_token"]
            _save_oauth(token)
            global _cached_oauth_token
            _cached_oauth_token = token
            return token
        error = data.get("error", "")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval = data.get("interval", interval + 5)
            continue
        raise RuntimeError(f"OAuth device flow error: {error} — {data.get('error_description', '')}")
    raise TimeoutError("User did not authorize in time.")


def _exchange_for_copilot_token(oauth_token: str) -> tuple[str, float]:
    """Exchange OAuth token for a short-lived Copilot API token.

    Returns (copilot_token, expires_at_epoch).
    """
    r = requests.get(
        COPILOT_TOKEN_URL,
        headers={
            "Authorization": f"token {oauth_token}",
            "Accept": "application/json",
            "Editor-Version": "vscode/1.100.0",
            "Editor-Plugin-Version": "copilot-chat/0.27.0",
        },
        timeout=15,
    )
    if r.status_code == 401:
        # OAuth token revoked or expired — need re-auth
        _clear_cached()
        raise RuntimeError("OAuth token expired. Please re-authorize GitHub Copilot.")
    r.raise_for_status()
    data = r.json()
    token = data["token"]
    # expires_at is Unix timestamp
    expires = data.get("expires_at", time.time() + 1800)
    if isinstance(expires, str):
        expires = float(expires)
    return token, expires


def get_copilot_token() -> str:
    """Get a valid Copilot API session token, refreshing if needed.

    Returns the Bearer token for api.githubcopilot.com.
    Raises RuntimeError if no OAuth token is available (user must authorize first).
    """
    global _cached_oauth_token, _cached_copilot_token, _copilot_token_expires

    with _lock:
        # Check if cached Copilot token is still valid (with 60s buffer)
        if _cached_copilot_token and time.time() < (_copilot_token_expires - 60):
            return _cached_copilot_token

        # Get OAuth token
        if not _cached_oauth_token:
            _cached_oauth_token = _load_cached_oauth()
        if not _cached_oauth_token:
            raise RuntimeError(
                "GitHub Copilot not authorized. Go to Settings and click 'Authorize Copilot'."
            )

        # Exchange for Copilot token
        token, expires = _exchange_for_copilot_token(_cached_oauth_token)
        _cached_copilot_token = token
        _copilot_token_expires = expires
        return token


def is_authorized() -> bool:
    """Check if we have a cached OAuth token (may still be expired)."""
    global _cached_oauth_token
    if _cached_oauth_token:
        return True
    _cached_oauth_token = _load_cached_oauth()
    return _cached_oauth_token is not None


def revoke():
    """Clear all cached tokens."""
    _clear_cached()
