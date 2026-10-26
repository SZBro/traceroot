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

---

## 2026-10-25 18:08: Changed: cut `claude -p` overhead with `--strict-mcp-config` and `--system-prompt`
**Type:** Changed, Result

**What:** the CLI backend now also passes `--strict-mcp-config` (don't load the user's MCP servers) and
`--system-prompt SYSTEM_PROMPT` (replaces Claude Code's built-in system prompt with one line: "reply
with only valid JSON"). `SYSTEM_PROMPT` lives with the other prompt constants in `claude_client.py`.

**Why:** step 3 showed each Claude call spending more tokens than the raw traceback + files it
replaces. Measured on the same tiny prompt:

| `claude -p` flags | Input tokens | List-price cost | Time |
|---|---|---|---|
| default | ~41,000 | $0.0031 | 5.2 s |
| `--tools ""` | ~15,000 | $0.0012 | 3.3 s |
| + `--strict-mcp-config` | ~5,400 | $0.0005 | 3.3 s |
| + `--system-prompt` | **~1,300** | **$0.0003** | 2.5 s |

Most of the old floor was the user's connected MCP servers plus Claude Code's own instructions.
TraceRoot needs neither, because every task instruction is already in our prompt.

**Result:** re-ran `medium_none_cart` to check that quality didn't drop. It gave the same #1 answer
(line 5, `load_cart`, confidence 0.60) and the same 4 alternatives in the same order. A full
analyze call went from ~7.8k to **~3.5k tokens** ($0.00105). 17/17 unit tests still pass.

**Decision:** keep `cli` as the default backend. With these flags its overhead is close to a raw API
call, and it needs no paid API key (it uses the user's Claude login and counts against plan usage
limits). The API backend stays optional (step 7) and goes in the README comparison.

---

## 2026-10-25 18:09: Decision: Jev API format from the SDK source
**Type:** Decision

**What:** read the installed `typesafe-sdk` 0.7.5 source (`question_types.py`, `response_types.py`,
`_schemas/models.py`, the sync client) instead of guessing. The format:
- Call `client.system_one(state=..., questions={name: Choice(instructions=..., criteria={label: description})})`.
- The answer is `res.choices[name]`, with `.choice` (top label), `.confidence`, and `.probabilities` (label → p).
- Usage is `res.usage.input_tokens` and `output_tokens`. Output tokens are free.
- Errors subclass `TypeSafeError`. The default timeout is 10 s (we use 30 s) with 2 retries. The key
  comes from `TYPESAFE_API_KEY`.

**Why:** the spec says not to invent API formats.

---

## 2026-10-25 18:10: Added: real `jev_client.py` (gate and score)
**Type:** Added

**What:**
- `gate()` asks one `choice` question over the 9 fixed categories, each with a description.
- `score()` asks one `choice` question whose options are Claude's candidates. The labels are
  candidate ids, because titles could collide; each description is the title plus `file:line`.
  It returns one probability per candidate in the original order, and rejects the answer if Jev's
  options don't match.
- With no key, a bad key, or any API error, it returns `None` with a one-line notice and never
  crashes. The key and request are never printed.
- It tracks Jev token usage, which goes into `meta.jev_tokens`.

**Decision:** every category description says the mistake is **on the crash line**, and
`other_or_complex` is "the bad value was created in a different function and passed along".

**Why:** the gate's quick answer points at the crash line. In the None-cart case the category
(`none_value`) is obvious, but the fix is 3 calls earlier. A gate that only judged the category
would confidently send the user to the wrong line.

---

## 2026-10-25 18:11: Result: gate tuning, threshold stays 0.8
**Type:** Result, Decision

**What:** `tests/fixtures/gate_report.py` runs only the gate on all 8 saved tracebacks
(8 Jev calls, no Claude):

| Test script | Gate pick | p | Should take |
|---|---|---|---|
| easy_missing_import | missing_import_or_module | 0.99 | gate |
| easy_typo_name | undefined_name_or_typo | 1.00 | gate |
| easy_file_not_found | file_not_found | 0.94 | gate |
| easy_wrong_args | wrong_arguments | 1.00 | gate |
| medium_none_cart | other_or_complex | 0.99 | full |
| medium_keyerror | other_or_complex | 0.96 | full |
| hard_off_by_one | other_or_complex | 0.95 | full |
| hard_str_int | other_or_complex | 0.96 | full |

Each gate call took about 70–90 ms (the first was ~850 ms with the TLS connection) and used
about 850–1,200 input tokens.

**Decision:** keep `GATE_THRESHOLD = 0.8`. The lowest correct easy pick is 0.94, so 0.8 leaves a margin.
The separation comes from the "on the crash line" category wording, not the threshold. All 4 harder
cases chose `other_or_complex` at ≥ 0.95, so no threshold value would have let them through.

**Caveat:** this is only 8 test scripts, and the easy ones have obvious messages
("Did you forget to import 'math'?"). Real-world errors will be closer calls.

---

## 2026-10-25 18:12: Result: full pipeline on all 8 test scripts (12 Jev + 4 Claude calls)
**Type:** Result

**What:** `python tests/fixtures/run_all.py` with real Jev and Claude:

| Test script | Path | Final #1 cause | Claude #1 | Jev #1 (p) | Agree |
|---|---|---|---|---|---|
| easy_missing_import | jev_gate | L2 NameError 'math' | - | L2 (0.99) | - |
| easy_typo_name | jev_gate | L5 NameError 'totl' | - | L5 (1.00) | - |
| easy_file_not_found | jev_gate | L5 FileNotFoundError | - | L5 (0.94) | - |
| easy_wrong_args | jev_gate | L6 missing arg 'age' | - | L6 (1.00) | - |
| medium_none_cart | full | L5 load_cart converts empty list to None | L5 | L5 (0.99) | yes |
| medium_keyerror | full | L3 build_profile stores user_name | L3 | L3 (0.96) | yes |
| hard_off_by_one | full | L4 page_bounds uses total+1 | L4 | L4 (0.97) | yes |
| hard_str_int | full | L10 qty never converted to int | L10 | L10 (0.87) | yes |

- **8/8 correct.** The gate handled 4/8 alone with no Claude call. On the other 4, Jev's
  independent score agreed with Claude's #1 every time, and every #1 is the exact planted line.
- Total time was 47 s. The gate path takes about 1 s per error; the full path about 10 s.
- Final order now comes from Jev's probability (`order_by = "jev"`). Claude's rank and confidence
  are kept beside it in `last.json`.
- Claude/Jev agreement was 4/4, so there are no disagreements to report yet. The test scripts
  have a single clear cause each; harder or ambiguous bugs would test the second opinion more.

---

## 2026-10-25 18:12: Added: Jev unit tests and `run_all.py` summary table
**Type:** Added

**What:** `tests/test_jev_client.py` adds 7 tests with fake Jev answers (no API calls):
- no key → `None` and a single notice
- gate output shape
- score keeps candidate order and rejects mismatched options
- gate decision: confident → no Claude call; p < threshold → Claude; `other_or_complex` at 0.99 → still Claude

`run_all.py` now prints a table with each script's path, Claude's #1 and Jev's #1 picks, and
whether they agree. Each script's header now prints before its output (`flush=True`).

**Why:** gate logic and fallbacks are tested without spending API calls. 24/24 tests pass.

---

## 2026-10-25 18:15: Added: `stats.py`, runs.csv logging, and `traceroot stats`
**Type:** Added

**What:**
- Every `analyze` appends one row to `.traceroot/runs.csv` with the spec's columns:
  `timestamp, error_type, path, gate_category, gate_p, claude_top, jev_top, agree, raw_tokens,
  returned_tokens, claude_tokens, jev_tokens, latency_ms, backend`.
- `claude_top` / `jev_top` are each model's #1 cause as `file:line`. `agree` is `yes` or `no` only on
  full runs where both models ranked.
- `returned_tokens` is measured from the **exact text `analyze` printed** (compact or `--json`).
- `raw_tokens` is the traceback plus the full contents of the referenced project files.
- Text token counts are `len // 4` estimates. Claude and Jev token counts are what their APIs report.
- `traceroot stats` prints: number of runs, % handled by the Jev gate alone, the Claude/Jev
  agreement rate, average raw vs returned tokens with the reduction, total model tokens
  (Claude + Jev), and a per-path table (average tokens and latency).
- 4 new unit tests (28 total, all passing).

**Why:** build step 5. These numbers feed the README results table.

---

## 2026-10-25 18:18: Result: `traceroot stats` on all 8 test scripts (12 Jev + 4 Claude calls)
**Type:** Result

**What:** this second full run reproduced step 4 exactly: **8/8 correct**, and every #1 is on the same
line. `traceroot stats`:

```
runs:                     8
handled by Jev gate alone: 4/8 (50%)
Claude/Jev agree on #1:    4/4 (100%)
agent tokens per run:      215 raw -> 58 returned (avg reduction 68%; estimates, len//4)
model tokens spent:        25644 total (Claude 12399, Jev 13245)

path        runs  avg Claude tok  avg Jev tok   avg ms
full           4            3100         2291     8660
jev_gate       4               0         1020      550
```

**Honest reading (for the README):**
- The calling agent reads about 68% fewer tokens (58 instead of 215). The test scripts are only
  6–25 lines, so this is a **floor**. Raw tokens grow with file size, while the returned output stays
  about 55–65 tokens.
- But **total model tokens spent (25.6k) are larger than the agent tokens saved** (~1.3k over
  8 runs). On files this small, TraceRoot isn't a net token win. Its value is (a) keeping the
  expensive agent's context small, since those tokens are spent by Haiku and Jev instead, and
  (b) the root-cause reasoning: in 4/8 cases the fix was in a different function from the crash.
- The Jev gate path costs about 1k tokens and 0.55 s, versus about 5.4k tokens and 8.7 s for the full
  path. The gate answering 50% of errors roughly halves the average cost.

---

## 2026-10-25 18:22: Added: `traceroot view` (HTML page + Mermaid diagram)
**Type:** Added

**What:**
- `traceroot view [n] [--no-open]` writes `.traceroot/view.html` and opens it in the browser. The page has:
  - the error line, the path taken (Jev gate or full), the gate pick, the ranking source, and
    model token counts
  - a Mermaid diagram for cause `n` (default 1), drawn by Claude from a new `DIAGRAM_PROMPT` in
    `claude_client.py`
  - every cause ranked, with Jev p (with a bar) and Claude confidence side by side, an
    agreement tag ("agree", or "Claude #2 · Jev #1"), the explanation, and the fix
  - a collapsible panel with the exact code slices that were sent to the models
- Mermaid loads with one `<script>` tag from `cdn.jsdelivr.net` (pinned `mermaid@10.9.1`) plus one
  init line with `securityLevel: "strict"`. There is no other JS. The CSS uses color tokens with a
  dark-mode variant.
- `last.json` now also stores `slices_text`, so the diagram prompt and code panel don't need to re-read files.
- `store.update()` rewrites `last.json` without resetting the `next` cursor.

**Why:** build step 6, the visual for humans. The agent keeps using the compact text.

---

## 2026-10-25 18:23: Decision: diagram safety, caching, and fallback
**Type:** Decision

**What:**
- **Cached:** each diagram is saved in `last.json` under its cause id, so reopening `view` makes no Claude call.
- **Validated:** `clean_mermaid()` accepts only `flowchart`/`graph` text, strips code fences, and
  rejects `<script>`, `javascript:`, and `click` directives. It also drops Claude's own `classDef`
  lines and adds ours (yellow = cause, red = crash).
- **Fallback:** if Claude fails or returns invalid Mermaid, plain code draws the call path from the
  traceback frames and attaches the cause node. The page says which kind of diagram it is showing.
- **Escaped:** all model text is HTML-escaped. A unit test checks that a candidate titled
  `<script>alert(1)</script>` comes out inert.

**Why:** model output is untrusted input to a page that runs JavaScript, and `view` should still
work when Claude is down.

---

## 2026-10-25 18:24: Result: view checked in a real browser
**Type:** Result

**What:**
- Claude's diagram for the None-cart case shows `checkout` → **`load_cart` line 5 sets items=None**
  (yellow) → `subtotal` → **`price_items` line 11 iterates None** (red). That's correct, and it shows
  the cause sitting off the crash path.
- `view 2` with a forced Claude failure rendered the code-built fallback diagram.
- `view 9` printed "cause 9 does not exist" (exit code 1).
- Checked in the desktop app's browser pane, served by a local static server
  (`.claude/launch.json` → `traceroot-view`). There were no console errors, the page worked in dark
  mode, and at phone width (375 px) there was no sideways scroll. Centered the diagram after the
  first look.
- 5 new unit tests (33 total, all passing): Mermaid validation, the fallback shape, HTML escaping,
  caching (Claude is called once across two renders), the fallback path, and an out-of-range `n`.
- Model cost for this step: 2 Claude calls (re-analyze + 1 diagram) and 2 Jev calls.
