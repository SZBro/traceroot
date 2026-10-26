"""Read/write .traceroot/last.json. The cursor lets `traceroot next` walk the ranked causes
without any model call."""
import json
from pathlib import Path

from . import config


def _path() -> Path:
    return config.STATE_DIR / "last.json"


def save(result: dict) -> Path:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    result["cursor"] = 0
    _path().write_text(json.dumps(result, indent=2), encoding="utf-8")
    return _path()


def update(result: dict) -> None:
    """Rewrite last.json keeping the current cursor (used to cache diagrams)."""
    _path().write_text(json.dumps(result, indent=2), encoding="utf-8")


def load() -> dict | None:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def advance() -> tuple[dict, int, int] | None:
    """Move the cursor forward. Returns (cause, index, total), or None when there are no more."""
    result = load()
    if not result:
        return None
    causes = result.get("causes") or []
    nxt = int(result.get("cursor", 0)) + 1
    if nxt >= len(causes):
        return None
    result["cursor"] = nxt
    _path().write_text(json.dumps(result, indent=2), encoding="utf-8")
    return causes[nxt], nxt, len(causes)
