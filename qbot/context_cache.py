"""Per-ticket cache for crawl snapshots + Bitbucket code context.

Re-running a pipeline for the same ticket (replays, repair iterations,
model experiments) used to re-crawl every page and re-fetch every diff.
This cache persists that context for a short TTL so repeated runs skip
straight to generation.

Cache entries are keyed by ticket key + target base URL and stored as JSON
under %APPDATA%/QBot/cache/. A cached crawl is only reusable while the
auth_state.json saved by that crawl still exists (the test runner needs it).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from qbot.config import config
from qbot.page_crawler import PageSnapshot
from qbot.paths import app_data_dir

CACHE_DIR = os.path.join(app_data_dir(), "cache")

# How long a cached crawl stays valid. Pages and linked commits rarely change
# within an hour of working the same ticket.
DEFAULT_TTL_SECONDS = 60 * 60


def _cache_path(ticket_key: str, base_url: str) -> str:
    h = hashlib.sha256(base_url.strip().lower().encode()).hexdigest()[:10]
    safe_key = "".join(c for c in ticket_key if c.isalnum() or c in "-_")
    return os.path.join(CACHE_DIR, f"{safe_key}_{h}.json")


def save_context(ticket_key: str, base_url: str,
                 snapshots: list[PageSnapshot], code_context: str) -> None:
    """Persist crawl snapshots + code context for this ticket. Best-effort."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        payload = {
            "ticket_key": ticket_key,
            "base_url": base_url,
            "timestamp": time.time(),
            "snapshots": [s.to_cache_dict() for s in snapshots],
            "code_context": code_context,
        }
        with open(_cache_path(ticket_key, base_url), "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        pass  # cache write failure must never break the pipeline


def load_context(ticket_key: str, base_url: str,
                 ttl_seconds: int = DEFAULT_TTL_SECONDS) -> tuple[list[PageSnapshot], str, float] | None:
    """Load cached context if fresh and the crawl's auth state still exists.

    Returns (snapshots, code_context, age_seconds) or None on miss.
    """
    path = _cache_path(ticket_key, base_url)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    age = time.time() - payload.get("timestamp", 0)
    if age > ttl_seconds:
        return None

    # Test execution reuses the auth state saved during the cached crawl —
    # without it the cache is useless (tests would hit the login wall).
    auth_state = os.path.join(config.test_output_dir, "auth_state.json")
    if not os.path.isfile(auth_state):
        return None

    snapshots = [PageSnapshot.from_cache_dict(d) for d in payload.get("snapshots", [])]
    if not snapshots:
        return None
    return snapshots, payload.get("code_context", ""), age


def invalidate(ticket_key: str, base_url: str) -> None:
    """Remove the cache entry for a ticket (used by 'Re-crawl')."""
    try:
        os.remove(_cache_path(ticket_key, base_url))
    except OSError:
        pass
