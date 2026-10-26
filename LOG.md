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

## 2026-10-25 18:19: Added: `traceroot view` (HTML page + Mermaid diagram)
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

## 2026-10-25 18:20: Decision: diagram safety, caching, and fallback
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

## 2026-10-25 18:22: Result: view checked in a real browser
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

---

## 2026-10-25 19:30: Decision: API backend deferred to future work
**Type:** Decision, Removed

**What:**
- The `api` Claude backend is **not built tonight**. `TRACEROOT_CLAUDE_BACKEND=api` gives a clear
  "not implemented yet; use cli" error.
- `claude_client._call_api` has a comment explaining what to implement (`anthropic` SDK,
  `SYSTEM_PROMPT`, `usage` tokens).
- Removed `anthropic` from `requirements.txt`. It stays as an optional extra in `pyproject.toml`.
- `.env.example` marks `ANTHROPIC_API_KEY` as "future, leave blank".

**Why:** it's first on the spec's cut list, and the user has no API key tonight, so it couldn't be
tested. Untested code in a graded repo is a liability. The user is open to adding it later
(they can generate a test key), or to another user contributing it, so the README lists it under
Future work. The backend comparison in the README still uses the real `claude -p` measurements.

---

## 2026-10-25 19:32: Added: Claude Code skill file
**Type:** Added

**What:** `.claude/skills/traceroot/SKILL.md` tells Claude Code that when a Python command fails, it should:
- run `traceroot analyze --run "<cmd>"`, or pipe the error in, **before** reading the traceback or opening files
- act on the top cause, opening only that file and line
- run `traceroot next` if the cause is wrong (no model call)
- use `traceroot view` only when the user asks for a visual

**Why:** build step 7. This is how an agent actually uses the tool. It's kept short on purpose,
because the skill itself costs context tokens.

---

## 2026-10-25 19:38: Added: README
**Type:** Added

**What:** the full README covers:
- what TraceRoot does, with a real example
- the architecture diagram
- the **Responsibilities** section: what Jev decides (gate + scorer), what Claude generates
  (candidates + diagram), and everything plain code does and checks
- install and `.env` setup, plus usage for every command and the skill
- the backend comparison (`claude -p` vs. the API: cost, latency, reliability) with the overhead table
- the per-script results table and `traceroot stats` output
- the Claude-vs-Jev comparison, a frank reading of the token numbers, limitations, and future work

**Why:** a graded requirement ("the README states exactly what the models are responsible for
and what the code checks").

---

## 2026-10-25 19:42: Result: fresh-clone install test
**Type:** Result

**What:** cloned the repo into a temporary folder and followed the README steps there (new venv,
`pip install -e .`).
- `.env`, `.venv`, and `.traceroot/` were **not** in the clone, so `.gitignore` works.
- `trt --help` works. `analyze --run` and the pipe form (`cmd 2>&1 | trt analyze`) both work.
- With no Jev key and Claude unavailable, it printed one notice per problem and fell back to the
  crash site, with no crash.
- `trt stats` works, and 33/33 unit tests pass in the clone.

**Not verified:** that Claude Code automatically picks up the skill in a live agent session. The
file format matches the skill convention (YAML frontmatter with `name` and `description`).

---

## 2026-10-25 19:44: Fixed: log timestamps for steps 6–7
**Type:** Fixed

**What:** corrected the times on the step 6 and step 7 entries to match when the work and its commits
actually happened. Step 7 entries had been stamped ~18:30 but were written ~19:30–19:42 (checked
against `git log`).

**Why:** this log is the graded record of the build, so its times should agree with the git history.

---

## 2026-10-25 19:53: Added: mutation benchmark (`bench/`) and project 1 ("shop")
**Type:** Added, Plan

**What:**
- **`bench/projects/shop/`:** a clean multi-file app (catalog from CSV, cart, pricing with tax and
  shipping, order receipts; 170 lines in 5 files).
- **`bench/cases.py`:** 9 mutations. Each one replaces one exact line, and that line is the ground
  truth. The cases are stored *outside* the project so the models never see them.
- **`bench/mutate.py`:** copies the project, applies one mutation, and confirms the program crashes.
- **`bench/run_bench.py`:** runs each case two ways and scores both against the mutated line
  (hit = right file, ±1 line):
  - **TraceRoot:** the real `traceroot analyze --run`
  - **Baseline:** the same Haiku model and prompt, given the traceback plus **every project file in
    full**, with no gate or Jev
- It also records the tokens an agent would read with and without TraceRoot. Results go to the
  git-ignored `bench/out/`, and the summary to the committed `bench/RESULTS.md`.

**Why:** the 8 original test scripts are tiny, single-file, and hand-written by the same model the
tool uses, so they can't support claims about accuracy or token savings. The user asked for real
numbers. Mutation gives automatic ground truth, cases where the bug is far from the crash, and less
author bias. Plan: one project at a time, then a full run.

---

## 2026-10-25 19:55: Result: benchmark v1 on "shop": TraceRoot loses to the full-file baseline
**Type:** Result

**What:** 9 cases:

| | Top-1 | Avg model tokens |
|---|---|---|
| TraceRoot (v1) | **4/9** | ~7,500 |
| Baseline (Claude + all files in full) | **9/9** | ~5,900 |

- TraceRoot was right on all 4 bugs on or next to the crash line. The Jev gate answered 2 of them for
  ~1.4–2.5k tokens.
- It **missed all 5** where the bug was elsewhere (raw rows kept in `bench/out/results_shop_v1.jsonl`).

**Why it missed:**
1. **4 misses: the bug file was never sent.** `catalog.py` (`load_catalog`, `find_product`) had
   already returned, so it isn't on the call stack. TraceRoot only reads files *in the traceback*.
   Claude often named the right idea ("price read from CSV without float conversion") but couldn't
   cite a file it was never shown, so it either gave no file or pointed at the call site.
2. **1 miss: the window was too narrow.** The `DISCOUNTS` dict was 44 lines above the crash, outside
   the ±20 window.
3. **Tokens:** on a 170-line project the ±20 windows are about as big as the whole files, and Jev adds
   ~3.7k tokens on the full path (gate + score). So TraceRoot cost *more* than sending everything.

**Takeaway:** the 8/8 on our own test scripts was misleading. The original test scripts were single
files, where the cause was always inside the window.

---

## 2026-10-25 20:06: Added: one-hop definition lookup in `trace_parser`
**Type:** Added, Fixed

**What:** `related_definitions()` (plain code, using Python's `ast`) looks at each traceback function,
finds the project names it uses, and adds **just their definitions** to the context:
- functions or classes imported from other project files (`from .catalog import load_catalog`,
  `from . import pricing` → `pricing.shipping_cost`)
- module-level constants and functions in the same file (e.g. `DISCOUNTS`)
- for classes, only the header and fields, not every method

Definitions already inside a ±20 window are skipped. Caps: 40 lines per definition, 160 in total
(`MAX_DEF_LINES`, `MAX_RELATED_LINES`). Each slice is labeled, e.g. "definition of load_catalog, used
in main()". The standard library and site-packages are never followed. One new unit test (34 total).

**Why:** benchmark v1 showed 5/9 misses because the bug was in code that had already returned
(not on the stack) or outside the window. A free pre-check showed all 5 bug lines now reach
the model, at ~1.2–1.5k tokens of code.

---

## 2026-10-25 20:09: Result: benchmark v2 on "shop" (with one-hop definitions)
**Type:** Result

| | Top-1 | Avg model tokens / case |
|---|---|---|
| TraceRoot v1 | 4/9 | ~7,500 |
| **TraceRoot v2** | **7/9** | ~8,000 |
| Baseline (Claude + all files) | 8/9 (9/9 in v1; the model varies) | ~5,850 |

- **Fixed:** shop-01, 02, and 09, where the bug was in `catalog.py`, which had already returned.
- **Still missed:**
  - **shop-03:** TraceRoot (and the baseline this time) named the right cause ("SAVE10 vs SAVE_10")
    but cited the lookup line (51), not the dict entry (7). Strict scoring counts that as a miss.
  - **shop-04:** Claude's own #1 was the better cause, but **Jev's re-ranking put a worse one first**.
- **Tokens:** on a 170-line project TraceRoot costs **~37% more** model tokens than sending
  everything. Jev is now ~4.6k per full-path case, about as much as Claude (~5.0k), because both its
  calls carry the code.
- **Agent side:** the calling agent reads **55 tokens instead of ~1,100** (95% less).

**Added to the benchmark:** a free comparison of TraceRoot's candidates ordered by Jev vs. by
Claude's own rank. On shop both orderings got 5/7 top-1.

**Next:** projects 2–4 with larger files, to see whether slicing pays off at more realistic sizes.

---

## 2026-10-25 20:14: Result: project 2 ("logs", 357 lines) and a token problem in the definition lookup
**Type:** Result

**What:**
- Added `bench/projects/logs/`, an access-log analyzer: regex parser, filters, stats (percentiles,
  top-N, histogram), report formatting, and a settings module, with 9 mutations.
- First run: TraceRoot got 7/9 top-1, the baseline 8/9. The Jev gate answered 3/9 at ~2.2–3.3k tokens
  vs. ~9k for the baseline.
- But full-path cases reached up to **15k tokens**. The lookup followed *every* name used by outer
  frames like `build_report()`, which calls a dozen report functions. That added 11–15 definitions
  (~2k tokens), and Jev's two calls each carried them too.

---

## 2026-10-25 20:19: Changed: precise definition lookup for outer frames
**Type:** Changed

**What:**
- The crash function is followed in full only if it's short (≤ `WHOLE_FUNC_LINES` = 12).
- Otherwise, and for every outer frame, TraceRoot follows only:
  - the statement on the frame line, narrowed to the innermost call when the statement spans several lines
  - plus the earlier local assignments that feed the names on it (two rounds of def-use, e.g.
    `cart = build_cart(order, catalog)` ← `catalog = load_catalog(...)`)

**Why:** this keeps exactly the definitions that fixed shop's misses and drops unrelated ones. A free
check on all 18 cases showed the same bug-line coverage, with average code sent dropping from
~1,200 to **859 tokens**. logs-07 went from 17 definitions to 4.

---

## 2026-10-25 20:20: Result: benchmark v3 on shop + logs (18 cases)
**Type:** Result

| | Top-1 | Gate-path tokens | Full-path tokens |
|---|---|---|---|
| TraceRoot v3 | **15/18** | ~1.7–2.5k (5 cases, all correct) | ~8.6–12.5k |
| Baseline (all files) | **17/18** | – | 5.0–10.0k (grows with project size) |

- Shop is now 8/9: shop-03 is fixed (the dict entry is in context), and shop-04 is at rank 5.
- Logs is 7/9. logs-01 is still missed: the `Record` is built in `parse_line`, which isn't on the stack
  or referenced by the crash frames' names (a two-hop case). logs-02 is at rank 2.
- On 170–360-line projects, the full path still costs about as much as sending every file, because
  ~4k of it is Jev.
- **Next:** projects 3–4 with larger code (~700 lines), where the baseline's cost should grow and
  TraceRoot's should stay about flat.

---

## 2026-10-25 20:25: Result: project 3 ("gradebook", 401 lines)
**Type:** Result

**What:** added `bench/projects/gradebook/` (models, CSV loader with validation, grading policy,
analytics, rendering) with 9 mutations. TraceRoot v3 got 6/9 top-1, the baseline 9/9. The gate
answered 3/9 correctly at ~2.5k tokens vs. ~10k.

**Misses:**
- **grade-04 (two hops):** Claude named the right cause ("assignment_from_row leaves max_points as a
  string") but cited the call site, because the body of a function *called inside* `load_course` was
  never sent.
- **grade-05:** a method on an object (`course.find_student`), which the lookup doesn't follow.
- **grade-03:** Jev ranked a candidate with no file first.

---

## 2026-10-25 20:30: Changed: second hop for definitions; tool frozen
**Type:** Changed, Decision

**What:** after hop-1 definitions, TraceRoot also adds project functions *called inside* them, capped at
`MAX_HOP2_LINES = 60` lines. A free check showed 23 of the 27 dev-set bug lines now reach the model.
Of the 4 that don't, 2 are missing-import cases scored at the crash line and 2 involve object methods.

**Decision:** **froze the tool at 20:31.** Projects 1–3 are the *development set*, because they were
used to make changes. Project 4 is written *after* the freeze as a **held-out set** and is never
used for tuning. This keeps the reported numbers from being overfit.

---

## 2026-10-25 20:45: Result: benchmark v4, development set (27 cases)
**Type:** Result

TraceRoot got **22/27 top-1 (25/27 in top 3)**; the baseline got 24/27. The gate answered 8/27, all
correct.

**Finding:** ordering TraceRoot's own candidates by *Claude's* rank would get 16/19 on the full
path, but *Jev's* order got 14/19. Jev's re-ranking is slightly hurting. It's left unchanged and
reported, because the tool is frozen.

---

## 2026-10-25 20:51: Result: held-out project ("planner", 315 lines, 9 cases)
**Type:** Result

**What:** `bench/projects/planner/` (dependency graph, topological sort, critical path, calendar with
holidays, Gantt chart), with 9 mutations decided before any run.

| Held-out | Top-1 | Avg model tokens |
|---|---|---|
| TraceRoot | **8/9** | 9,431 |
| Baseline | **8/9** | 8,617 |

The gate answered 3/9, all correct, at ~3.4k tokens vs. ~8.4k. TraceRoot found plan-01 (the
`UNIT_DAYS` constant), which the baseline missed. It missed plan-04 (an object method,
`project.get`), as on the dev set.

---

## 2026-10-25 20:52: Result: final benchmark numbers (36 cases)
**Type:** Result, Decision

| Errors | Cases | TraceRoot top-1 | Baseline top-1 | TraceRoot model tok | Baseline model tok | Agent context (baseline → TraceRoot) |
|---|---|---|---|---|---|---|
| **Simple (gate)** | 11 | 11/11 | 11/11 | **2,966 (−65%)** | 8,412 | **2,100 → 52 (−98%)** |
| Complex | 25 | 19/25 | 21/25 | 11,072 (+23%) | 8,981 | 1,735 → 59 (−97%) |
| All | 36 | 30/36 (83%) | 32/36 (89%) | 8,595 (−2%) | 8,807 | 1,846 → 57 (−97%) |

**Decision (with the user):** position TraceRoot as **cheaper, cleaner debugging for simple errors**.
It cuts both model tokens (−65%) and the error text put into the agent's context (−98%), with equal
accuracy. For complex errors, the honest claim is a much smaller agent context (−97%) at somewhat
lower accuracy and higher model spend.

**Also:**
- Added a "simple vs. complex" table to `run_bench.py`, and a dev vs. held-out split.
- Added 7 unit tests for the benchmark's scoring and case building (`tests/test_bench.py`).
  41 tests pass in total.
- Rewrote the README Results section around these numbers, with the weak spots under Limitations.

---

## 2026-10-25 21:04: Plan: v5 improvement experiment (keep only what helps)
**Type:** Plan, Decision

**Rule:** every change goes behind a setting, so v4 can be reproduced exactly. v4's results are
saved in `bench/versions/v4_results.jsonl` and `v4_RESULTS.md`. A change is **kept only if it doesn't
make the numbers worse**; otherwise the setting is switched back to its v4 value and the result is
logged anyway. Projects 1–4 (36 cases) are now all "seen", so a **new held-out project 5** is written
for the final comparison, and both v4 and v5 run on it.

**Changes and hypotheses (written before testing):**

| # | Change | Setting (v4 → v5) | Hypothesis | Evidence from v4 |
|---|---|---|---|---|
| A | Widen the Jev gate | `GATE_THRESHOLD` 0.8 → **0.65** | +1 case on the cheap path, precision stays 100% | shop-08 (missing arg, on the crash line) was gated `wrong_arguments` at 0.66; the only other non-`other` gate pick on the full path is logs-04 at 0.51, which would be wrong, so the threshold must stay above it. Every other full-path case was truly complex, so the gate is near its ceiling. |
| C | Jev from re-ranker to **agreement checker** | `TRACEROOT_RANK_BY` jev → **claude** | full-path top-1 rises from 19/25 to ~21/25. When Jev's pick differs, show it as an `alt:` line, so the agent sees 2 causes for ~20 more tokens | Claude's own order beat Jev's order (21/25 vs. 19/25) |
| D | Leaner Jev context | `TRACEROOT_JEV_CONTEXT` all → **windows** | the gate and scorer get the traceback plus crash windows only, not the one-hop definitions, cutting ~1–2k Jev tokens per complex case | Jev was ~40% of full-path tokens (both calls carried all definitions) |

**Metrics:** the same as v4 (top-1, top-3, model tokens, agent context), plus "hit shown up front"
(the #1 cause or the `alt:` line).

---

## 2026-10-25 21:06: Added: v5 settings, benchmark version switch, held-out project 5 ("library")
**Type:** Added

**What:**
- **New settings in `config.py`, with v5 defaults:**
  - `GATE_THRESHOLD` = 0.65
  - `TRACEROOT_RANK_BY` = `claude` (`jev` reproduces v4)
  - `TRACEROOT_JEV_CONTEXT` = `windows` (`all` reproduces v4)
- **Full-path output:**
  - Ranked by Claude.
  - `pipeline.agreement()` records whether Jev's top pick matches cause #1.
  - The compact output now says `Jev agrees` or `Jev prefers #k`, plus an `alt (Jev's pick, #k): ...`
    line when they disagree.
- **`bench/run_bench.py --config v4|v5`:** sets these settings explicitly for each run. The local
  `.env` had `GATE_THRESHOLD=0.8`, which would otherwise have silently overridden the new default.
  - `--out` writes to a separate results file.
  - `--baseline-from` reuses earlier baseline answers, since the baseline didn't change, which saves
    the Claude calls.
  - New metric: `shown_hit`, the right cause shown up front, either as #1 or on the `alt:` line.
- **`.env.example`:** now 0.65. **The user's own `.env` still says 0.8 and should be updated by hand.**
- **4 new unit tests** for Claude ranking, the agreement check, and the `alt:` line (45 total, all pass).
- **`bench/projects/library/`:** a lending system (catalog, ISBN search index, member tiers, loans,
  fines, event replay; 291 lines) with 9 mutations, written *after* the v5 changes. It's the fresh held-out
  set, and it deliberately includes one known-weak "object method" case (lib-04).

---

## 2026-10-25 21:10: Result: v5a on the 36 known cases, change A reverted
**Type:** Result, Decision, Removed

**What:** v5a = A + C + D (threshold 0.65, Claude ranking, lean Jev context), compared with v4 on the
same 36 cases (`bench/compare.py`):

| Metric | v4 | v5a |
|---|---|---|
| Top-1 | 30/36 | 30/36 |
| Top-3 | 33/36 | 32/36 |
| Right cause shown up front (#1 or `alt:`) | 30 | 31 |
| Gate answered / correct | 11 / 11 | 12 / **11** |
| Avg model tokens | 8,595 | **6,979 (−19%)** |
| Gate-path tokens | 2,966 | **2,018** |
| Full-path tokens (Jev part) | 11,072 (5,457) | **9,460 (3,894)** |

**Per change:**
- **A (threshold 0.65): REVERTED.** It let **logs-04 through as a wrong quick answer**. With the
  leaner context from D, Jev's confidence that the KeyError is local rose from 0.51 to 0.70: it no
  longer sees the `THRESHOLDS` definition in `settings.py`, so the error looks local. The gate's whole
  value is being right when it answers, and 11/12 breaks that. shop-08, the case A was meant to add,
  fell to 0.62 and wasn't added anyway. **Lesson:** A and D interact, so changes have to be judged
  together, not one at a time.
- **C (Claude ranking + Jev agreement): KEPT.** logs-08 went from rank 2 to rank 1 and shop-04 from
  rank 3 to rank 2, with no full-path losses.
- **D (lean Jev context): KEPT, conditionally.** It cuts ~1.6k tokens per full-path case and ~0.9k per
  gate case. At the 0.8 threshold, logs-04 (0.70) goes back to the Claude path. grade-08 (0.77, was
  0.83) also moves to the Claude path: still expected to be correct, just more expensive.

**Next:** final v5 = 0.8 + C + D. Rerun the 36 known cases for clean numbers (not a simulation),
then run v4 vs. v5 on the fresh held-out project 5. `.env.example` is back to 0.8, so the user's
`.env` needs no change.

---

## 2026-10-25 21:16: Result: final v5 (threshold 0.8 + C + D) on the 36 known cases
**Type:** Result

| Metric | v4 | **v5** | Baseline |
|---|---|---|---|
| Top-1 | 30/36 | **31/36** | 32/36 |
| Gate answered / correct | 11 / 11 | 11 / **11** | – |
| Avg model tokens | 8,595 | **7,255 (−16%)** | 8,807 |
| Gate path / full path | 2,966 / 11,072 | **2,007 / 9,565** | – |
| Jev tokens on full path | 5,457 | **3,900** | – |

- **Changed for the better:** shop-04 (rank 3 → 1), logs-02 (2 → 1), logs-08 (2 → 1).
- **Changed for the worse:**
  - **shop-01:** a hit in v4, a miss in v5. Claude gave the right cause ("CSV price never converted to
    float in load_catalog"), but with no valid file, so the validator nulled the path. It isn't caused by
    a v5 change: Claude's prompt and context are identical, so it's model variance. Logged as a
    limitation (strict file matching).
  - **plan-01:** rank 1 → 3.
- The earlier test collision on `bench/out/work/shop-01` did *not* affect this case: the run had no
  errors, and the causes were complete. `tests/test_bench.py` now builds into a temporary folder, so
  this can't happen again.

---

## 2026-10-25 21:19: Result: held-out project 5 ("library"), v4 vs. v5
**Type:** Result

| 9 fresh cases | v4 | **v5** | Baseline |
|---|---|---|---|
| Top-1 | 5/9 | **6/9** | **9/9** |
| Simple (gate) | 4/4, 2,876 tok | **4/4, 2,052 tok** | 4/4, ~7,950 tok |
| Complex (full path) | 1/5, 11,068 tok | **2/5, 10,405 tok** | 5/5, ~8,450 tok |
| Avg model tokens | 7,427 | **6,693** | 8,327 |

**Honest reading:**
- v5 beats v4 on the fresh set (lib-02 went from rank 2 to rank 1, and tokens fell 10%).
- But **TraceRoot is clearly behind the baseline on complex errors here (2/5 vs. 5/5)**. All three
  misses involve data flowing through *object attributes or methods*: `self.books[isbn].copies`
  (lib-01), `self.members.find(...)` (lib-04), and `self.joined` in a method 24 lines from the parser
  (lib-09). The definition lookup follows names, not attributes. The dev projects had fewer of these.
- On simple errors TraceRoot is excellent: 4/4 at about a quarter of the baseline's tokens.

---

## 2026-10-25 21:21: Decision: ship v5, final numbers, README updated
**Type:** Decision, Changed

**Decision:** v5 (threshold 0.8, Claude ranking with a Jev agreement check, lean Jev context) is
**kept as the default**. It's better than or equal to v4 on every aggregate metric on both the known
and held-out cases. Change A stays reverted.

**Final numbers (v5, all 45 cases):**

| Errors | Cases | TraceRoot top-1 | Baseline top-1 | TraceRoot tokens | Baseline tokens | Agent context |
|---|---|---|---|---|---|---|
| Simple (gate) | 15 | **15/15** | 15/15 | **2,019 (−76%)** | 8,309 | **2,051 → 51 (−98%)** |
| Complex | 30 | 22/30 | 26/30 | 9,705 (+9%) | 8,912 | 1,736 → 65 (−96%) |
| All | 45 | 37/45 (82%) | 41/45 (91%) | **7,143 (−18%)** | 8,711 | 1,841 → 61 (−97%) |

v4 on the same 45 cases: 35/45 at 8,361 tokens. On v5's complex cases, Jev's order would get 18/30
and Claude's 22/30.

**Bookkeeping:**
- `bench/versions/` holds the raw v4, v5a, and v5 results.
- `bench/out/results.jsonl` and `bench/RESULTS.md` are now v5.
- planner is reclassified as *dev* for v5, because v5 was designed from results that included it.
- `bench/compare.py` compares any two versions.

**README:**
- The headline is now "simple errors: −76% model tokens, −98% agent context, same accuracy".
- Complex errors are described honestly (73% vs. 87%, and 2/5 on the held-out set).
- The v4 → v5 experiment table includes the reverted change.
- The Jev responsibility now reads "second opinion / agreement check".
- New limitations and future work: follow object attributes and methods, a 3-way gate, fuzzy path
  matching.

---

## 2026-10-25 21:32: Plan: v6 improvement round (keep only what helps)
**Type:** Plan

**Order of work:**
1. **Write held-out project 6 *before* any code change**, so its bugs can't be shaped to suit the
   new features.
2. Implement the two changes behind settings.
3. A free context check.
4. v6 on the 45 known cases, reusing the baseline's answers.
5. v5 vs. v6 on project 6.
6. Keep or revert each change.

Hard stop for development is 22:45.

| # | Change | Setting | Hypothesis | Evidence |
|---|---|---|---|---|
| F | **Follow object methods:** when the code calls `x.m(...)` and exactly **one** project class defines `m`, add that method's definition | `TRACEROOT_FOLLOW_METHODS` (off = v5) | Fixes "object method" misses like `directory.find`, `course.find_student`, `project.get` (lib-04, grade-05, plan-04) for a few hundred extra tokens. It won't fix attribute data flow (`self.books[isbn].copies`). | The 3 held-out complex misses and 2 dev misses go through objects. |
| P | **Fuzzy paths:** if Claude cites a file that doesn't exist, but exactly **one** project file has that file name, use it | `TRACEROOT_FUZZY_PATHS` (off = v5) | Rescues right answers with a slightly wrong path (shop-01 in v5). Accepts only a unique name match, so the "no invented files" rule mostly holds. | shop-01: Claude named the right cause, but the path was dropped. |

**Known downsides (discussed with the user):** F is a heuristic, since Python types are unknown; common
method names are skipped when several classes define them. Extra context can distract the model, and
the change is designed from cases we've already seen (hence the new project). P slightly loosens file
validation.

---

## 2026-10-25 21:34: Added: held-out project 6 ("bank"), committed before any v6 code
**Type:** Added

**What:** `bench/projects/bank/`, a ledger app: money parsing, accounts and a `Bank` class, CSV
transactions with deposits, withdrawals, and transfers, interest and fees, and statements (277 lines).
It has 9 mutations of the usual kinds. Two of them happen to involve the targeted "object method"
pattern (bank-03 `bank.lookup`, bank-09 `self.opened` via `days_open`). That's just how ordinary
object-style code looks, and the mutations weren't picked for the new feature.

**Why commit now:** the git timestamp shows the held-out cases existed before F/P were written.
library is reclassified as *dev* for v6, because v6 is designed from its misses.
