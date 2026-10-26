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

---

## 2026-10-25 17:56: Added: `claude_client.py` (cli backend)
**Type:** Added

**What:**
- `ask_claude(prompt, schema_hint) -> dict`, with the prompts kept as constants at the top of the file.
- The CLI backend runs `claude -p --output-format json --model <TRACEROOT_CLAUDE_MODEL> --tools ""`
  from a temporary neutral folder, sending the prompt on **stdin**.
- It trusts `is_error` over `subtype` and extracts the JSON defensively (strips code fences, then
  takes the first `{` to the last `}`).
- It retries once with a "return ONLY JSON" reminder.
- It records backend, latency, real token usage, and cost in `_meta`.
- The `api` backend raises a clear "not built yet" error until step 7.

**Why:** build step 3. Stdin avoids Windows' ~32k-character command-line limit on big prompts.
A one-call test returned `{"ok": true}` (~15k tokens, $0.0007, 5.5 s).

**Decision:** added a `category` field (one of the 9 gate categories) to the candidate JSON schema.
The compact output's first line (`[1/4] none_value ...`) needs a category for every cause, not only
gate answers.

---

## 2026-10-25 17:57: Added: `store.py` and a placeholder `jev_client.py`
**Type:** Added

**What:** `store.save/load/advance` reads and writes `.traceroot/last.json` with a `cursor`, so
`next` makes no model calls. `jev_client.gate()` and `score()` currently return `None`
("Jev unavailable").

**Why:** gets `analyze` → `next` working end to end before adding Jev in step 4. The `None`
return is the same fallback path the real client uses when there's no key or the API fails.

---

## 2026-10-25 17:58: Added: `pipeline.py` (orchestration, validation, ranking)
**Type:** Added

**What:**
- Flow: parse → Jev gate → (if not confident) Claude candidates → Jev score → validate → rank →
  save. The gate counts as confident only if p ≥ `GATE_THRESHOLD` and the category isn't
  `other_or_complex`.
- Validation (plain code):
  - drops candidates without a title and renames duplicate ids
  - nulls any file that doesn't exist or isn't safe to read (so `.env` can never be cited), and its line
  - nulls probabilities outside 0–1
  - maps unknown categories to `other_or_complex`
  - caps the list at 6
- Ranking: Jev probability when every cause has one, otherwise `claude_rank`. Both rankings and
  `order_by` are saved.
- If Claude fails, the result is a single "crash site" cause instead of a crash (`source = "fallback"`).
- Saves `meta` for step 5's stats: backend, Claude tokens and cost, `raw_tokens` (traceback + full
  referenced files, `len // 4`), and latency.

**Why:** the spec's "plain code validates everything": the models suggest, the code checks.

---

## 2026-10-25 17:59: Added: `analyze` and `next` commands
**Type:** Added

**What:** `traceroot analyze` accepts `--run "cmd"`, a traceback file, raw error text, or stdin, plus
`--file PATH` and `--json`. `traceroot next [--json]` prints the next cause, or
`no more candidates; try traceroot analyze with --file`. Compact output matches the spec format.
`view` and `stats` print "arrives in step N" for now. stdout is forced to UTF-8 for Windows.

**Why:** build step 3's goal: `analyze` and `next` working end to end.

---

## 2026-10-25 18:00: Result: end-to-end runs, Claude only (3 Claude calls)
**Type:** Result

**What:** Claude's #1 cause hit the **exact planted line** on all three non-trivial test scripts:

| Test script | Claude's #1 cause | Planted bug | Match |
|---|---|---|---|
| medium_none_cart | `none_value` at line 5: "load_cart replaces empty cart list with None" (0.60) | line 5 | yes |
| hard_off_by_one | `key_or_index_error` at line 4: "page_bounds uses total + 1" (0.85) | line 4 | yes |
| hard_str_int | `wrong_type` at line 10: "qty kept as string, never converted" (0.85) | line 10 | yes |

- None-cart is the notable one: Claude found `load_cart`, which is **not in the traceback**, from the
  merged code slice. Causes #2–#4 were sensible alternatives (guard in price_items, validate in
  subtotal, `not items` vs `is None`).
- Edge cases checked with no model spend (forced backend failure): a command that exits 0, no input,
  Claude failing (falls back to the crash site), non-Python text, and piped stdin.
- Unit tests: 17 pass (11 parser + 6 new pipeline tests for validation, ranking, and output format).

**Finding (for the README):** on these tiny test scripts, Claude spends **more** tokens (~7.8k, mostly
Claude Code's fixed system prompt) than the "raw" traceback + files (~313). TraceRoot's saving is
in the **calling agent's context** (it reads 4 short lines instead of the traceback and files), and
it grows with file size. The Jev gate exists to skip that Claude call on easy errors, and step 4
will show how often it does.
