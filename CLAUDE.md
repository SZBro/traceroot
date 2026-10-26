# TraceRoot: trace an error back to its root cause, with fewer agent tokens

Name: **TraceRoot**. Package: `traceroot`. CLI commands: `traceroot` and the short alias `trt`
(both registered as console scripts in pyproject.toml). Do NOT use `tr` as the alias: `tr` is a
standard Unix command and shadowing it would break shell scripts.

## What this project is

A **local Python CLI** that a coding agent (Claude Code) or a human runs on an error/traceback.
Instead of the agent reading a huge traceback and opening several files, `traceroot` returns a
compact, ranked root cause, one cause at a time. A human can open a local HTML view with the
ranked list and a Mermaid diagram.

Two models, each with a small, clear job:
- **Jev** (TypeSafe AI, decision-only model): a cheap gate ("is this an easy, common error?")
  and an independent scorer of candidate causes. Jev returns probabilities, never text.
- **Claude**: generates candidate causes (with its own ranking) and draws diagrams.

**Plain Python does everything else**: parsing, file reading, validation, ranking, saving, logging, rendering.

This is Artifact 3 ("AI Inside It") for TCSS 490. **Due tonight, Sun Oct 25, 11:59 PM.**
Requirements to be "complete":
1. A model does real work every time it runs.
2. The repo contains a log of plans and changes (`LOG.md`, see below).
3. The README states exactly what the models are responsible for and what the code checks.
(The student then adds a portfolio card with a repo link / demo video and a short reflection.)

Keep it small and working. Prefer a working simple version over an ambitious broken one.

---

## Architecture

```
agent (via skill) / human
        │
   traceroot CLI  (analyze | next | view | stats)
        │
 trace_parser  ── parse Python traceback, grab ±20 lines around top 2–3 frames   [code]
        │
   Jev gate    ── choose among fixed common categories, with confidence           [Jev]
     │      │
 confident  unsure
     │      └─ Claude: 3–6 candidate causes + Claude's own rank & confidence      [Claude]
     │                 │
     │         Jev scores the candidates (independent second opinion)            [Jev]
     │                 │
     └──────► rank, validate, save .traceroot/last.json, log stats                  [code]
                       │
      top cause (compact) │ next cause (from file, no model call) │ HTML view
```

### Files

```
traceroot/
  __init__.py
  cli.py            # argparse entry point: analyze, next, view, stats
  config.py         # settings: gate threshold, categories, model names, paths (env-overridable)
  trace_parser.py   # parse Python tracebacks → frames; read code slices safely
  jev_client.py     # all Jev calls (gate + score); fallback when no key
  claude_client.py  # ask_claude(prompt) with two backends: `claude -p` (default) and API
  pipeline.py       # orchestrates the flow above; returns a Result object
  store.py          # read/write .traceroot/last.json (cursor for `next`)
  stats.py          # append run stats to .traceroot/runs.csv; token estimates
  render_html.py    # writes .traceroot/view.html (ranked list + Mermaid) and opens it
tests/fixtures/     # planted-bug Python scripts + saved tracebacks for demos/tests
.claude/skills/traceroot/SKILL.md   # tells Claude Code to use the tool
README.md
LOG.md
.env.example
.gitignore
requirements.txt
pyproject.toml      # so `pip install -e .` gives a `traceroot` command
```

Python 3.10+. Keep dependencies minimal: `python-dotenv`, `anthropic` (optional backend),
and the official TypeSafe Python SDK (`typesafe-sdk`) if it works; otherwise plain `requests`
against the HTTP API.

---

## Component details

### trace_parser.py (plain code, no AI)
- Accept traceback text (from a file, stdin, or `--run "python script.py"` which runs the command
  and captures stderr).
- Parse Python `File "path", line N, in func` frames and the final `ExceptionType: message` line.
- Take the **last 3 frames** (closest to the crash) that are inside the project root.
- Read ±20 lines around each frame's line. Mark the error line.
- **Safety rules:** never read files outside the project root; never read `.env`, `*.pem`,
  `*.key`, or anything in `.git/`; skip files from site-packages / the standard library.
- Optional `--file path` flag for errors with no traceback.
- Non-Python errors: still analyzed, just without auto source context.

### jev_client.py
- Key from env var `TYPESAFE_API_KEY`. Official API: `https://api.typesafe.ai/v1/systemone`,
  model `jev-latest`. Test key: `GET https://api.typesafe.ai/v1/models`.
- **Before writing this file, read the real docs (docs.typesafe.ai) or the installed SDK's source
  for the exact request/response format.** Do not guess the schema. Jev supports question types
  like choice (pick one of N options), score, and boolean ("noul"); we mainly need **choice**,
  which returns a probability per option and a confidence.
- `gate(error_text, code_slices) -> {category, probability, confidence}`
  Fixed categories (in config.py, easy to edit):
  `missing_import_or_module, undefined_name_or_typo, wrong_type, none_value, wrong_arguments,
   key_or_index_error, file_not_found, syntax_error, other_or_complex`
  Treat it as **confident** only if the top probability ≥ `GATE_THRESHOLD` (default 0.8, env-overridable)
  **and** the top category is not `other_or_complex`.
- `score(error_text, code_slices, candidates) -> list of probabilities`, using each candidate's
  short title as an option.
- Input limit is about 64k tokens; truncate code slices if needed.
- **No key / API error → return None**, and the pipeline falls back to Claude-only ranking. Print a
  one-line notice, never crash.

### claude_client.py
- One function: `ask_claude(prompt: str, schema_hint: str) -> dict`.
- Backend chosen by env `TRACEROOT_CLAUDE_BACKEND` = `cli` (default) or `api`.
  - `cli`: run `claude -p "<prompt>" --output-format json` via subprocess with a timeout. The JSON
    envelope's result field holds the model's text; extract the JSON object from it defensively
    (strip code fences, find first `{` to last `}`).
  - `api`: Anthropic Python SDK, key from `ANTHROPIC_API_KEY`, model from env `TRACEROOT_CLAUDE_MODEL`
    (default `claude-haiku-5-5`), small `max_tokens`.
- Retry once on invalid JSON with a "return only valid JSON" reminder. Then fail with a clear error.
- Record the backend, latency, and token usage if available (API gives usage; for the CLI, estimate).

**Candidate prompt** asks for ONLY this JSON:
```json
{"candidates": [
  {"id": "c1", "title": "short title, <= 10 words",
   "explanation": "1-3 sentences", "file": "path or null", "line": 0,
   "fix_hint": "one sentence", "claude_rank": 1, "claude_confidence": 0.0}
]}
```
3–6 candidates. Tell Claude to base its reasoning on the traceback and code slices given, and not to invent files.

**Diagram prompt** (only for `view`, for one chosen cause): returns `{"mermaid": "flowchart TD ..."}`
showing the call path from the entry point to the crash and where the cause enters.

### pipeline.py
1. Parse → frames and slices.
2. Jev gate. If confident → build one "quick answer" result from the category, the error line, and
   the frame (no Claude call). Mark `source = "jev_gate"`.
3. Otherwise → Claude candidates → Jev score → **final order = Jev probability**, falling back to
   `claude_rank` when Jev is unavailable. Keep both rankings in the saved result.
4. Validate everything (required fields, probabilities 0–1, file paths exist or null).
5. Save to `.traceroot/last.json` with `cursor = 0`; log stats.

### store.py, `next`
- `traceroot next` reads `last.json`, advances the cursor, and prints the next cause. **No model calls.**
  When there are no more causes: print "no more candidates; try `traceroot analyze` with `--file`".

### Output formats
- **Compact (default for analyze/next)**, built for agents, few tokens:
  ```
  [1/4] none_value (p=0.82) orders.py:40
  cause: cart.items set to None when the cart is empty
  fix: return early or use [] instead of None
  more: `traceroot next`
  ```
- `--json` flag prints the same as JSON.
- `traceroot view [n]`: writes `.traceroot/view.html` with all causes ranked (Jev p and Claude
  confidence side by side, agreement marker), then asks Claude for a Mermaid diagram of cause n
  (default 1) and opens it in the browser. Mermaid is loaded with one `<script>` tag from
  `cdn.jsdelivr.net`. Clean, readable styling; no other JS.

### stats.py
Append one row per `analyze` to `.traceroot/runs.csv`:
`timestamp, error_type, path(jev_gate|full), gate_category, gate_p, claude_top, jev_top, agree,
 raw_tokens, returned_tokens, claude_tokens, jev_tokens, latency_ms, backend`
- `raw_tokens` = estimated tokens of the full traceback + the full contents of the referenced
  project files (what an agent would otherwise read).
- `returned_tokens` = tokens of the compact output.
- Token estimate: `len(text) // 4` is fine (say so in the README).
- `traceroot stats` prints a summary: runs, % handled by the Jev gate alone, Claude/Jev agreement
  rate, average token reduction, total model tokens spent.

---

## Claude Code skill: `.claude/skills/traceroot/SKILL.md`
Tell Claude Code: when a Python command fails with a traceback, run
`traceroot analyze --run "<the failing command>"` (or pipe the error in) **before** reading the
traceback in full or opening files. Act on the top cause; if it's wrong, run `traceroot next`.
Use `traceroot view` only when the user wants a visual. Keep the skill short.

---

## Security and config
- `.env` (git-ignored) holds `TYPESAFE_API_KEY`, optional `ANTHROPIC_API_KEY`,
  `TRACEROOT_CLAUDE_BACKEND`, `TRACEROOT_CLAUDE_MODEL`, `GATE_THRESHOLD`.
- `.env.example` with blank values is committed. **Never commit keys. Never print keys.**
- `.gitignore`: `.env`, `.traceroot/`, `__pycache__/`, `*.egg-info/`, `.venv/`.
- Each user uses their own keys (bring your own key). Nothing is hosted.

---

## Test fixtures (`tests/fixtures/`)
Create small Python scripts with planted bugs, plus a `run_all.sh` / `run_all.py` that runs
`traceroot analyze --run` on each:
- easy: missing import, typo'd variable name, file not found, wrong number of args
- medium: `None` passed down three functions (like the cart/checkout example), KeyError from a
  misspelled dict key built elsewhere
- harder: off-by-one causing an IndexError two calls away; a type mix-up (str vs int) from parsing input
Easy ones should mostly hit the Jev gate; harder ones should go through Claude. This is the demo data.

---

## Build order (time-boxed; it's ~4pm, due 11:59pm)
1. **Setup (15m):** venv, pyproject, `.gitignore`, `.env.example`, empty modules, LOG.md started.
   Verify the Jev key with the `/v1/models` call. Verify `claude -p` works.
2. **trace_parser + fixtures (30m)**, with a couple of unit tests.
3. **claude_client (cli backend) + pipeline without Jev (30m)** → `analyze` and `next` working end to end.
4. **jev_client: score, then gate (45m).** Read the docs first. Tune the threshold on the fixtures.
5. **stats + `traceroot stats` (20m).**
6. **render_html + `view` (40m).**
7. **Skill file, README, API backend (30m).**
8. **Run all fixtures, record results in LOG.md, demo (rest).**

If short on time, cut in this order: API backend → `view` diagram (keep the list) → stats summary
command. Never cut: analyze, next, Jev scoring, LOG.md, README responsibilities section.

## Out of scope (list as future work in the README)
MCP server, hosted website, VS Code extension, non-Python traceback parsing, auto-run hook,
diagrams for every cause.

---

## LOG.md: keep it updated as you go
After each build step, append a short dated entry: what was planned, what changed, what broke, and
decisions (e.g., the threshold value and why). Also record notable results (gate hit rate,
Claude/Jev disagreements). This is a graded requirement.

**Format: changelog style.** Every change or addition gets its own section, appended at the bottom
(never fold it into an older entry):
```
## YYYY-MM-DD HH:MM: <Type>: <short title>
**Type:** Plan | Added | Changed | Fixed | Removed | Decision | Result
**What:** what changed (files, behavior)
**Why:** the reason
(optional) **What broke:** / **Decision:**
```
Write the entry in the same step as the change, before committing, not in a batch at the end.

## README must include
- What it does, plus install and usage (`pip install -e .`, `.env` setup, the commands).
- **Responsibilities section**: what Jev decides, what Claude generates, what plain code
  checks/does.
- Backends (`claude -p` vs API): tradeoffs in cost, latency, and reliability.
- Results table from the fixtures (`traceroot stats` output) and the Claude-vs-Jev comparison.
- Limitations (models only see the trace and slices; token counts are estimates) and future work.

## Working style for the agent
- Small steps; run the code after each step. Use the fixtures to test.
- Don't invent API formats; check the docs or the SDK source.
- Keep model prompts in one place (`claude_client.py` constants) so they're easy to tweak.
- Ask the user before anything that spends noticeable money (e.g., loops of many API calls).
