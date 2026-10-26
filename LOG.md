# TraceRoot development log

A changelog of plans and changes. Each change gets its own dated section, newest at the bottom.
Each entry says **what** changed and **why**, plus anything that broke and any decisions made.

Entry types: **Plan**, **Added**, **Changed**, **Fixed**, **Removed**, **Decision**, **Result**.

---

## 2026-10-25 16:15: Plan: build plan agreed
**Type:** Plan

**What:**
- `traceroot` / `trt` CLI with `analyze`, `next`, `view`, and `stats`.
- Plain code parses the Python traceback, keeps the last 3 in-project frames, and reads ±20 lines
  around each one (never `.env`, key files, `.git/`, site-packages, or the stdlib).
- The Jev gate picks one of 9 fixed categories. Confident (p ≥ 0.8 and not `other_or_complex`)
  means a quick answer with no Claude call.
- Otherwise Claude proposes 3–6 candidates with its own rank. Jev scores them independently, and
  the final order uses Jev's probability (falling back to Claude's rank when Jev is unavailable).
- Code validates the result, saves `.traceroot/last.json` (the cursor for `next`, which makes no
  model calls), and logs a row to `runs.csv` with token estimates (`len // 4`).
- `view` writes an HTML page with the ranked list and a Mermaid diagram from Claude.

**Why:** to agree on scope before writing code. Cut order if we run late: API backend → `view`
diagram → `stats` summary.

---

## 2026-10-25 16:28: Added: project skeleton and packaging
**Type:** Added

**What:**
- `traceroot/` package with empty modules: `cli`, `config`, `trace_parser`, `jev_client`,
  `claude_client`, `pipeline`, `store`, `stats`, `render_html`.
- Folders: `tests/fixtures/` and `.claude/skills/traceroot/`.
- `pyproject.toml` with console scripts `traceroot` and `trt`, both pointing to
  `traceroot.cli:main` (a stub for now). `anthropic` is an optional extra (`pip install -e .[api]`).
- `.gitignore` (`.env`, `.traceroot/`, `__pycache__/`, `*.egg-info/`, `.venv/`), `.env.example` with
  blank values, `requirements.txt`, and a `README.md` stub.

**Why:** build step 1 in CLAUDE.md. `pip install -e .` needs `pyproject.toml` to create the
commands. The alias is `trt` and not `tr`, because `tr` is a standard Unix command.

---

## 2026-10-25 16:30: Added: virtual environment and dependencies
**Type:** Added

**What:** created `.venv` on Python 3.13.5 and installed python-dotenv, requests, anthropic, and
`typesafe-sdk` 0.7.5. `pip install -e .` works, and both `traceroot` and `trt` run.

**Why:** `typesafe-sdk` is the official TypeSafe AI SDK on PyPI (author: TypeSafe AI, typesafe.ai).
We'll read its source before writing `jev_client.py` instead of guessing the API schema.

---

## 2026-10-25 16:35: Added: own git repository for TraceRoot
**Type:** Added

**What:** ran `git init -b main` inside the TraceRoot folder and confirmed with `git check-ignore`
that `.env` and `.venv/` are ignored.

**Why:** the enclosing git repository was rooted at the user's whole home directory, so committing
there could have swept in unrelated personal files. TraceRoot now has its own repo; a GitHub remote
gets added later.

---

## 2026-10-25 16:45: Result: Jev API key verified
**Type:** Result

**What:** `GET https://api.typesafe.ai/v1/models` returned HTTP 200 and listed `jev-latest` and
`jev-preview`. We'll use `jev-latest`. The key is read from `.env` and never printed.

**Why:** step 1 requires confirming the key works before building `jev_client.py`.
`ANTHROPIC_API_KEY` stays blank because the default `cli` backend doesn't use it.

---

## 2026-10-25 17:00: Fixed: `claude` CLI not on PATH, login expired
**Type:** Fixed

**What:**
- `claude` was not on PATH. The only copy was bundled with the Claude desktop app under a versioned
  folder.
- Installed the standalone Claude Code CLI (2.1.310) to `~/.local/bin`, added it to the user PATH,
  and logged in again.
- Added `TRACEROOT_CLAUDE_BIN` to `.env.example` so the client can point at any `claude` binary.

**What broke:** before the re-login, `claude -p` failed with "OAuth session expired". Even on that
failure the JSON envelope said `subtype: "success"` while `is_error` was `true`.

**Decision:** `claude_client` checks `is_error`, not `subtype`.

---

## 2026-10-25 17:05: Result: `claude -p` JSON shape and token overhead
**Type:** Result, Decision

**What:** `claude -p --output-format json --model claude-haiku-5-5` works and returns `result` =
`{"ok": true}`. Useful envelope keys: `result` (the model text), `is_error`, `usage`
(input/output/cache tokens), `total_cost_usd`, `duration_ms`, `terminal_reason`, `session_id`.

Overhead on a tiny prompt:

| Setup | Input tokens | Cost | Time |
|---|---|---|---|
| Default tools | ~41k | $0.0031 | 5.2 s |
| `--tools ""` | ~15k | $0.0012 | 3.3 s |

**Decision:** the CLI backend runs with `--tools ""`, `--model` from `TRACEROOT_CLAUDE_MODEL`, and a
neutral working directory, so Claude sees only the traceback and code slices we send.

**Why:** cutting tools makes calls about 2.6× cheaper and stops Claude from reading files on its
own. The remaining ~15k-token floor is Claude Code's own system prompt, so it's a tradeoff to name
in the README's backend comparison.

---

## 2026-10-25 17:10: Changed: LOG.md restructured as a changelog
**Type:** Changed

**What:** rewrote this file from a single "step 1" summary into one dated section per change, each
with a type, what changed, and why.

**Why:** the course wants a log of plans and changes that reads like a changelog, where every
addition or change is its own dated, explained entry.
