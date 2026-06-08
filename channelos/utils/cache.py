"""
ChannelOS — Cache utilities
Generic 24h file-based cache used by TrendResearchAgent and YouTubeTrendsAgent.
"""

import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

CACHE_DIR = Path("cache")
CACHE_TTL_HOURS = 24


def cache_key(raw: str) -> str:
    """MD5 hex digest of a string — used as cache filename suffix."""
    return hashlib.md5(raw.encode()).hexdigest()


def cache_get(key: str, namespace: str = "generic") -> dict | list | None:
    """
    Return cached payload if it exists and is not expired.
    Returns None on miss or expiry.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"{namespace}_{key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if datetime.fromisoformat(data["expires_at"]) < datetime.now():
            path.unlink(missing_ok=True)
            return None
        return data["payload"]
    except Exception:
        return None


def cache_set(key: str, payload: dict | list, namespace: str = "generic") -> None:
    """Persist payload to cache with a 24h TTL."""
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"{namespace}_{key}.json"
    path.write_text(
        json.dumps(
            {
                "expires_at": (datetime.now() + timedelta(hours=CACHE_TTL_HOURS)).isoformat(),
                "payload": payload,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
