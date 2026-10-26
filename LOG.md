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

---

## 2026-10-25 17:50: Decision: step 2 ground rules
**Type:** Decision

**What:** before starting step 2, the user agreed to the following:
- The `cli` backend passes `--model` (Haiku) and `--tools ""` and runs from a neutral directory.
- The model-call budget is about 10–16 Jev calls and about 5 Claude calls per full test run.
- Windows tweaks: `run_all.py` only (no `.sh`). The gate threshold starts at 0.8 and gets tuned on
  the test scripts.
- Commit at the end of each step, so git history matches this log.

**Why:** to settle cost and behavior before writing model code.

---

## 2026-10-25 17:51: Added: `config.py` settings
**Type:** Added

**What:** `traceroot/config.py` holds the project root (cwd, or `TRACEROOT_ROOT`), `.traceroot/` state
dir, `MAX_FRAMES=3`, `CONTEXT_LINES=20`, blocked files/dirs, the 9 gate categories,
`GATE_THRESHOLD` (default 0.8), and the model names. `claude_bin()` finds `claude` via
`TRACEROOT_CLAUDE_BIN`, then PATH, then `~/.local/bin`. It loads `.env` from the current folder
first and TraceRoot's own folder second.

**Why:** the spec keeps every tunable setting in one env-overridable place.

---

## 2026-10-25 17:51: Added: `trace_parser.py` (plain code, no AI)
**Type:** Added

**What:**
- `parse_traceback()`:
  - parses `File "...", line N, in func` frames, including SyntaxError frames with no `in func`
  - keeps the source line under each frame and skips Python 3.11 `^^^` caret lines
  - for chained exceptions, uses only the **last** traceback (the one that crashed)
  - reads the final `Type: message` line, with a fallback for custom exception names such as
    `CartEmpty`
- `attach_context()` keeps the last 3 frames inside the project and reads ±20 lines around them.
- Safety (`resolve_in_project`): never reads outside the project root, `.env*`, `*.pem`, `*.key`,
  `.git/`, `site-packages`, `.venv`, or the standard library.
- `run_command()` runs `--run` commands in the project root and captures stderr, with a 60 s timeout.
- `slice_for_file()` handles `--file` with no traceback.
- Non-Python errors still parse, with `is_python = False` and no slices.

**Why:** build step 2. All file reading and safety checks are plain code, so the models only ever
see what this module chose to send.

---

## 2026-10-25 17:52: Added: 8 planted-bug test scripts and `run_all.py`
**Type:** Added

**What:** `tests/fixtures/` holds 4 easy cases (missing import, typo'd name, file not found, missing
argument), 2 medium cases (None passed down 3 calls, mismatched dict key built elsewhere), and 2 hard
cases (off-by-one IndexError two calls away, str vs float from parsing). `run_all.py` runs
`traceroot analyze --run` on each script (calls models), or with `--capture` only saves each
traceback to `tests/fixtures/tracebacks/` (no models). All 8 crash as intended.

**Why:** demo and tuning data. The easy cases should hit the Jev gate; the medium and hard cases
should go through Claude.

---

## 2026-10-25 17:53: Fixed: test scripts gave away the answer
**Type:** Fixed

**What:** removed the "Planted bug: ..." docstrings and `# bug: ...` comments from all 8 scripts.
The bug descriptions now live only in `run_all.py`'s `FIXTURES` table. A unit test now fails if the
word "bug" appears in any traceback or code slice.

**Why:** those comments landed inside the ±20-line code slices, so Claude and Jev could have read
the answer instead of reasoning about it. That would have made the results meaningless.

---

## 2026-10-25 17:53: Changed: merge overlapping code slices
**Type:** Changed

**What:** `read_slice()` became `read_slices()`. Frames in the same file get one merged window when
their ±20-line ranges overlap or touch, and every frame line is marked `>>` (`CodeSlice.marks`).

**Why:** in the None-cart case all 3 frames are in one 25-line file, which would have sent three
near-identical copies of the code. Now every fixture produces exactly **one** slice of 6–25 lines.
That matters because the whole point of TraceRoot is fewer tokens.

---

## 2026-10-25 17:54: Changed: saved tracebacks use project-relative paths
**Type:** Changed

**What:** `run_all.py --capture` removes the absolute project path and converts backslashes to `/`
in the `File "..."` lines.

**Why:** absolute paths exposed the local username and broke the saved tracebacks on other
machines.

---

## 2026-10-25 17:54: Result: parser unit tests pass
**Type:** Result

**What:** `python -m unittest discover tests` runs 11 tests and all pass. They cover:
- every test script crashes and parses
- the None-cart frames, the merged slice, and that `items = None` (the real cause) is inside the window
- chained exceptions, SyntaxError, custom exception names, non-Python errors
- slice merging for overlapping and far-apart lines
- safety: `.env`, `.pem`, `.key`, `.git`, site-packages, outside-root and stdlib files are refused

**Notable:** in the None-cart case, `load_cart` (the real cause) is **not in the traceback at all**,
because it already returned. It's only visible because the ±20-line window around `checkout`
covers it. This is the kind of case the Claude path exists for.
