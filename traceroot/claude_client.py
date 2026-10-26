"""All Claude calls. One entry point, ask_claude(), with two backends: `claude -p` (default) and the API.
Prompts live here as constants so they're easy to tweak."""
import json
import re
import subprocess
import tempfile
import time

from . import config

CANDIDATE_PROMPT = """You are debugging a Python error. Propose the most likely ROOT causes, not just the crash line.
The root cause is often earlier than the crash: where a bad value was created, not where it blew up.

Base your reasoning ONLY on the error, traceback and code slices below. Do not invent files, functions or
line numbers. Use a file path exactly as shown in the slices, or null if the cause is not in the shown code.
In the slices, lines marked ">>" are lines from the traceback.

Return 3 to 6 candidates, best first. Return ONLY this JSON, no prose, no code fences:
{schema}

Rules: "title" <= 10 words. "explanation" 1-3 sentences. "fix_hint" one sentence.
"category" is exactly one of: {categories}.
"claude_rank" is 1 for the most likely. "claude_confidence" is your probability (0.0-1.0) that this
candidate is the real root cause; the values should roughly sum to 1 or less.

ERROR:
{error_line}

TRACEBACK (may be trimmed):
{traceback}

CODE SLICES:
{slices}
"""

CANDIDATE_SCHEMA = """{"candidates": [
  {"id": "c1", "title": "short title", "explanation": "1-3 sentences", "category": "none_value",
   "file": "path or null", "line": 0, "fix_hint": "one sentence",
   "claude_rank": 1, "claude_confidence": 0.0}
]}"""

# Replaces Claude Code's built-in system prompt for the cli backend (and is the system prompt for
# the api backend). All task instructions live in the user prompt, so this only sets the format.
SYSTEM_PROMPT = "You are a precise debugging assistant. Reply with only valid JSON, no prose."

RETRY_SUFFIX ="\n\nYour previous reply was not valid JSON. Return ONLY the JSON object, nothing else."


class ClaudeError(RuntimeError):
    pass


def ask_claude(prompt: str, schema_hint: str = "") -> dict:
    """Send `prompt`, return the parsed JSON object. Retries once on invalid JSON.
    The returned dict has a `_meta` key: backend, latency_ms, tokens, cost_usd."""
    backend = config.CLAUDE_BACKEND
    call = _call_cli if backend == "cli" else _call_api if backend == "api" else None
    if call is None:
        raise ClaudeError(f"unknown TRACEROOT_CLAUDE_BACKEND={backend!r} (use cli or api)")

    tokens, cost, started = 0, 0.0, time.perf_counter()
    text = ""
    for attempt in range(2):
        text, t, c = call(prompt if attempt == 0 else prompt + RETRY_SUFFIX)
        tokens, cost = tokens + t, cost + c
        data = extract_json(text)
        if data is not None:
            data["_meta"] = {"backend": backend, "latency_ms": int((time.perf_counter() - started) * 1000),
                             "tokens": tokens, "cost_usd": round(cost, 5), "attempts": attempt + 1}
            return data
    raise ClaudeError(f"Claude did not return valid JSON after a retry. Last reply started: {text[:200]!r}")


def extract_json(text: str) -> dict | None:
    """Pull a JSON object out of model text: strip code fences, take first `{` to last `}`."""
    if not text:
        return None
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _call_cli(prompt: str) -> tuple[str, int, float]:
    """`claude -p` from a neutral folder, prompt on stdin (avoids Windows arg limits).
    Tools off, no MCP servers, and our own system prompt: cuts overhead from ~41k to ~1.3k tokens."""
    exe = config.claude_bin()
    if not exe:
        raise ClaudeError("`claude` not found. Install Claude Code or set TRACEROOT_CLAUDE_BIN in .env.")
    cmd = [exe, "-p", "--output-format", "json", "--model", config.CLAUDE_MODEL, "--tools", "",
           "--strict-mcp-config", "--system-prompt", SYSTEM_PROMPT]
    with tempfile.TemporaryDirectory(prefix="traceroot-") as neutral:
        try:
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", cwd=neutral, timeout=config.CLAUDE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            raise ClaudeError(f"`claude -p` timed out after {config.CLAUDE_TIMEOUT_S}s")
    try:
        env = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ClaudeError(f"`claude -p` returned non-JSON (exit {proc.returncode}): "
                          f"{(proc.stderr or proc.stdout)[:200]!r}")
    # `subtype` can say "success" on auth failures, so trust `is_error`.
    if env.get("is_error"):
        raise ClaudeError(f"`claude -p` failed: {env.get('result')}")
    u = env.get("usage") or {}
    tokens = sum(int(u.get(k) or 0) for k in
                 ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"))
    return env.get("result") or "", tokens, float(env.get("total_cost_usd") or 0.0)


def _call_api(prompt: str) -> tuple[str, int, float]:
    raise ClaudeError("the api backend is not built yet (build step 7); use TRACEROOT_CLAUDE_BACKEND=cli")


def candidates_prompt(error_line: str, traceback: str, slices: str) -> str:
    return CANDIDATE_PROMPT.format(schema=CANDIDATE_SCHEMA, categories=", ".join(config.CATEGORIES),
                                   error_line=error_line, traceback=traceback, slices=slices)
