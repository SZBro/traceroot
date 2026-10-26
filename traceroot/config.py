"""Settings for TraceRoot. Everything here can be overridden with an env var or .env file."""
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

# Settings are read from (first wins): real environment variables, ./.env in the folder you run
# traceroot from, your user config ~/.traceroot/.env (works from any project), TraceRoot's own .env.
TOOL_DIR = Path(__file__).resolve().parent.parent
USER_CONFIG = Path(os.environ.get("TRACEROOT_CONFIG") or Path.home() / ".traceroot" / ".env")
load_dotenv(Path.cwd() / ".env")
load_dotenv(USER_CONFIG)
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
MAX_DEF_LINES = 40      # one-hop definitions: max lines per definition
MAX_RELATED_LINES = 160 # one-hop definitions: max lines in total
WHOLE_FUNC_LINES = 12   # crash function this short: follow every name in it
MAX_HOP2_LINES = 60     # second hop (functions called inside hop-1 definitions): max lines in total
RUN_TIMEOUT_S = 60      # timeout for `analyze --run`

# Files we never read, even inside the project root
BLOCKED_NAMES = {".env"}
BLOCKED_SUFFIXES = {".pem", ".key"}
BLOCKED_DIRS = {".git", "site-packages", "dist-packages", ".venv", "venv", "__pycache__"}

# Jev gate
GATE_THRESHOLD = _float("GATE_THRESHOLD", 0.8)    # 0.65 was tried in v5 and reverted (LOG.md 21:10)

# How the full path ranks causes: "claude" (v5: Claude's order, Jev checks agreement) or "jev" (v4: Jev re-ranks)
RANK_BY = os.environ.get("TRACEROOT_RANK_BY", "claude").strip().lower()
# What code Jev sees: "windows" (v5: traceback + crash windows) or "all" (v4: + one-hop definitions)
JEV_CONTEXT = os.environ.get("TRACEROOT_JEV_CONTEXT", "windows").strip().lower()
# v6 experiment (LOG.md 21:32): follow `obj.method()` calls to the one project class defining `method`
FOLLOW_METHODS = os.environ.get("TRACEROOT_FOLLOW_METHODS", "1").strip() not in ("0", "false", "no", "")
# v6 experiment: accept a cited file that doesn't exist if exactly one project file has that name
FUZZY_PATHS = os.environ.get("TRACEROOT_FUZZY_PATHS", "1").strip() not in ("0", "false", "no", "")
MAX_PROJECT_FILES = 400  # project scan limit for the two features above
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
