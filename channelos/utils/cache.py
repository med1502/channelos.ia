"""
ChannelOS — Shared cache helpers
Unified JSON-file cache with expiry used by trend_agent and youtube_agent.
"""

import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

CACHE_DIR = Path("cache")
CACHE_TTL_HOURS = 24


def cache_key(text: str) -> str:
      """Return an MD5 hex digest of the given text."""
      return hashlib.md5(text.encode()).hexdigest()
def cache_get(prefix: str, key: str) -> dict | None:
      """
          Return the cached payload for (prefix, key) if it exists and hasn't expired.
              Returns None on cache miss or expiry.
                  """
      CACHE_DIR.mkdir(exist_ok=True)
      path = CACHE_DIR / f"{prefix}_{key}.json"
      if not path.exists():
                return None
            data = json.loads(path.read_text())
    if datetime.fromisoformat(data["expires_at"]) < datetime.now():
              return None
          return data["payload"]


def cache_set(prefix: str, key: str, payload: dict) -> None:
      """Persist payload under (prefix, key) with a TTL of CACHE_TTL_HOURS hours."""
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"{prefix}_{key}.json"
    path.write_text(json.dumps({
              "expires_at": (datetime.now() + timedelta(hours=CACHE_TTL_HOURS)).isoformat(),
              "payload": payload,
    }, ensure_ascii=False))
