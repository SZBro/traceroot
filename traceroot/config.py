"""Settings for TraceRoot. Everything here can be overridden with an env var or .env file."""
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

# .env in the folder you run traceroot from wins; TraceRoot's own .env is the fallback.
TOOL_DIR = Path(__file__).resolve().parent.parent
load_dotenv(Path.cwd() / ".env")
load_dotenv(TOOL_DIR / ".env")


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# Paths
PROJECT_ROOT = Path(os.environ.get("TRACEROOT_ROOT") or Path.cwd()).resolve()
STATE_DIR = PROJECT_ROOT / ".traceroot"

# Parsing
MAX_FRAMES = 3          # frames closest to the crash that we keep
CONTEXT_LINES = 20      # lines read above and below each frame's line
RUN_TIMEOUT_S = 60      # timeout for `analyze --run`

# Files we never read, even inside the project root
BLOCKED_NAMES = {".env"}
BLOCKED_SUFFIXES = {".pem", ".key"}
BLOCKED_DIRS = {".git", "site-packages", "dist-packages", ".venv", "venv", "__pycache__"}

# Jev gate
GATE_THRESHOLD = _float("GATE_THRESHOLD", 0.8)
CATEGORIES = [
    "missing_import_or_module",
    "undefined_name_or_typo",
    "wrong_type",
    "none_value",
    "wrong_arguments",
    "key_or_index_error",
    "file_not_found",
    "syntax_error",
    "other_or_complex",
]

# Models
JEV_MODEL = os.environ.get("TRACEROOT_JEV_MODEL", "jev-latest")
JEV_TIMEOUT_S = 30.0
CLAUDE_BACKEND = os.environ.get("TRACEROOT_CLAUDE_BACKEND", "cli").strip().lower() or "cli"
CLAUDE_MODEL = os.environ.get("TRACEROOT_CLAUDE_MODEL", "claude-haiku-5-5").strip() or "claude-haiku-5-5"
CLAUDE_TIMEOUT_S = 120


def claude_bin() -> str | None:
    """Path to the claude executable: TRACEROOT_CLAUDE_BIN, then PATH, then the default install dir."""
    explicit = os.environ.get("TRACEROOT_CLAUDE_BIN", "").strip()
    if explicit:
        return explicit
    found = shutil.which("claude")
    if found:
        return found
    default = Path.home() / ".local" / "bin" / ("claude.exe" if os.name == "nt" else "claude")
    return str(default) if default.exists() else None
