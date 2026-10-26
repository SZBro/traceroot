# TraceRoot

**Trace an error back to its root cause, with fewer agent tokens.**

TraceRoot is a local Python CLI that you, or a coding agent like Claude Code, run on a failing
command. A coding agent would normally read a long traceback and open several files. TraceRoot
returns a compact, ranked root cause instead, one at a time:

```
$ traceroot analyze --run "python tests/fixtures/medium_none_cart.py"
[1/3] none_value (p=0.98) tests/fixtures/medium_none_cart.py:5
cause: load_cart sets items to None for empty carts
fix: Keep items as an empty list (remove the None assignment) so downstream iteration always receives an iterable.
more: `traceroot next`
```

The crash in that example happens in `price_items` (line 11), three calls away. TraceRoot points
at `load_cart` (line 5), where the bad value is created. That function isn't in the traceback at all.

Commands: `traceroot` or the short alias `trt` (not `tr`, which is a standard Unix command).

---

## How it works

```
agent (via skill) / human
        │
   traceroot CLI  (analyze | next | view | stats)
        │
 trace_parser  ── parse the traceback, read ±20 lines around the last 3 project frames   [code]
        │
   Jev gate    ── pick one of 9 fixed error categories, with a probability                  [Jev]
     │      │
 confident  unsure
     │      └─ Claude: 3–6 candidate causes, with Claude's own rank and confidence        [Claude]
     │                 │
     │         Jev scores the candidates (independent second opinion)                    [Jev]
     │                 │
     └──────► validate, rank, save .traceroot/last.json, log stats                          [code]
                       │
   top cause (compact) │ `next` (from file, no model call) │ `view` (HTML + diagram)
```

## Responsibilities: what each part does

TraceRoot uses two models, each with one small job. Plain Python does everything else and checks
everything the models return.

### Jev (TypeSafe AI, `jev-latest`): **decides**, returns probabilities, never text
1. **Gate:** "Is this an easy, common error whose fix is on the crash line?" Jev answers one
   `choice` question over 9 fixed categories (`missing_import_or_module`, `undefined_name_or_typo`,
   `wrong_type`, `none_value`, `wrong_arguments`, `key_or_index_error`, `file_not_found`,
   `syntax_error`, `other_or_complex`). If the top category has p ≥ `GATE_THRESHOLD` (0.8) and isn't
   `other_or_complex`, TraceRoot answers right away and **Claude is never called**.
2. **Scorer:** on the full path, Jev independently scores Claude's candidates (one probability each).
   **The final order is Jev's probability.** Claude's own ranking is kept beside it for comparison.

### Claude (`claude-haiku-5-5` via `claude -p`): **generates** text
1. **Candidate causes:** 3–6 root-cause hypotheses as strict JSON (title, explanation, category,
   file, line, fix hint, Claude's rank and confidence). It sees only the traceback and code slices
   we send.
2. **Diagram** (`view` only): a Mermaid flowchart of the call path for one chosen cause.

### Plain Python: **does and checks** everything else
- **Parsing:** reads Python tracebacks, including chained exceptions (only the last one counts),
  SyntaxErrors, custom exception names, and Python 3.11 caret lines.
- **Safe file reading:** reads only inside the project root. It never reads `.env*`, `*.pem`,
  `*.key`, `.git/`, `site-packages`, `.venv`, or the standard library. Overlapping ±20-line windows
  in the same file are merged, so code is never sent twice.
- **Validating Claude's output:**
  - drops candidates without a title and renames duplicate ids
  - clears any file that doesn't exist or isn't allowed, plus its line (so Claude can't cite `.env`
    or an invented file)
  - discards probabilities outside 0–1
  - maps unknown categories to `other_or_complex`
  - caps the list at 6
- **Validating Jev's output:** rejects scores whose options don't match the candidates. Malformed
  diagrams are rejected, and model text is HTML-escaped in the view.
- **Ranking and decisions:** applies the gate threshold, and ranks by Jev, falling back to Claude
  when Jev is unavailable.
- **Saving and fallbacks:** `last.json` holds the ranked list and a cursor, so `next` makes **no**
  model calls. Diagrams are cached.
  - Claude down: you get the crash site.
  - Jev down or no key: ranking is by Claude only.
  - Diagram fails: plain code draws the call path from the traceback.
- **Stats:** one CSV row per run, with token estimates.

## Install

Requires Python 3.10+ and [Claude Code](https://claude.com/claude-code) (the `claude` command,
logged in). You also need your own TypeSafe API key; nothing is hosted, and each user brings their
own keys.

```bash
git clone <this-repo-url> traceroot
cd traceroot
python -m venv .venv
.venv/Scripts/activate          # Windows (Git Bash). macOS/Linux: source .venv/bin/activate
pip install -e .
cp .env.example .env            # then put your TYPESAFE_API_KEY in .env
```

`.env` is git-ignored and never printed. Settings in `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `TYPESAFE_API_KEY` | (none) | Jev key. Without it TraceRoot still works, ranking by Claude only. |
| `TRACEROOT_CLAUDE_BACKEND` | `cli` | How Claude is called (only `cli` exists today). |
| `TRACEROOT_CLAUDE_MODEL` | `claude-haiku-5-5` | Model for candidates and diagrams. |
| `TRACEROOT_CLAUDE_BIN` | (auto) | Path to `claude` if it isn't on PATH. |
| `GATE_THRESHOLD` | `0.8` | Minimum Jev probability for a gate-only answer. |

## Usage

```bash
traceroot analyze --run "python app.py"     # run a command and analyze its stderr
python app.py 2>&1 | traceroot analyze       # or pipe an error in
traceroot analyze error.txt                  # or a saved traceback file (or the error text itself)
traceroot analyze --file src/orders.py err.txt   # also send a file the traceback doesn't show
traceroot analyze --json ...                 # full JSON (explanation, both rankings)

traceroot next        # next-ranked cause, from .traceroot/last.json (no model call)
traceroot view [n]    # HTML page: all causes ranked + a Mermaid diagram of cause n (default 1)
traceroot stats       # summary of every run in .traceroot/runs.csv
```

**With Claude Code:** `.claude/skills/traceroot/SKILL.md` tells Claude Code to run `traceroot analyze`
on a failing Python command **before** reading the traceback or opening files, to act on the top
cause, and to run `traceroot next` if that cause is wrong.

## Claude backends: `claude -p` vs. the API

Today TraceRoot calls Claude through the Claude Code CLI (`claude -p --output-format json`). An API
backend (the `anthropic` SDK with an `ANTHROPIC_API_KEY`) is planned but **not implemented yet**.
`TRACEROOT_CLAUDE_BACKEND=api` gives a clear error. See Future work.

| | `cli` (implemented) | `api` (future) |
|---|---|---|
| **Cost** | No extra key. Counts against your Claude plan's usage limits. | Pay per token on a separate API bill; anyone running the tool needs a key. |
| **Latency** | Starts a process each call: ~2.5 s for a tiny prompt, ~8–9 s for a real analyze. | Faster: no process startup. |
| **Reliability** | Depends on the `claude` install and login (we hit an expired login once). Errors can report `subtype: "success"`, so we check `is_error`. | Fewer moving parts; clearer error codes. |
| **Token overhead** | Large by default, fixed with flags (below). | Close to zero beyond our prompt. |

**What we measured on `claude -p` overhead** (same tiny prompt):

| Flags | Input tokens | List-price cost | Time |
|---|---|---|---|
| default | ~41,000 | $0.0031 | 5.2 s |
| `--tools ""` | ~15,000 | $0.0012 | 3.3 s |
| + `--strict-mcp-config` | ~5,400 | $0.0005 | 3.3 s |
| + `--system-prompt <ours>` | **~1,300** | **$0.0003** | 2.5 s |

TraceRoot uses all three flags and runs `claude` from a temporary empty folder. That way Claude
can't use tools or read files, and it sees only what TraceRoot sends.

## Results

Eight test scripts with planted bugs live in `tests/fixtures/`, with no hints in the code. Run them
all with `python tests/fixtures/run_all.py`.

| Test script | Planted bug | Path | #1 cause | Claude #1 | Jev #1 (p) | Agree |
|---|---|---|---|---|---|---|
| easy_missing_import | `math.sqrt` without `import math` | Jev gate | L2 | – | L2 (0.99) | – |
| easy_typo_name | `totl` for `total` | Jev gate | L5 | – | L5 (1.00) | – |
| easy_file_not_found | missing `settings/config.json` | Jev gate | L5 | – | L5 (0.94) | – |
| easy_wrong_args | missing `age` argument | Jev gate | L6 | – | L6 (1.00) | – |
| medium_none_cart | `items = None` in `load_cart` (L5), crash 3 calls later | full | **L5** | L5 | L5 (0.98) | yes |
| medium_keyerror | dict built with `user_name`, read as `username` (L3) | full | **L3** | L3 | L3 (0.90) | yes |
| hard_off_by_one | `total + 1` in `page_bounds` (L4), IndexError in another function | full | **L4** | L4 | L4 (0.98) | yes |
| hard_str_int | `qty` never `int()`-ed in `parse_order` (L10), crash in `line_total` | full | **L10** | L10 | L10 (0.99) | yes |

**8/8 correct**, and every #1 is the exact planted line. Two full runs gave the same results.

`traceroot stats` after those 8 runs:

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

**Claude vs. Jev:** on the full path, Jev's independent score picked the same #1 as Claude every
time. Jev was often *more* decisive: on the None-cart case it gave the top cause 0.98–0.99 across
runs, while Claude's own confidence was 0.60–0.80.
These test scripts each have one clear cause, so they don't produce disagreements; ambiguous bugs
would test the second opinion more.

**The gate:** what made it work was the wording, not the threshold. Each category's description
says the mistake is **on the crash line**, and `other_or_complex` means "the bad value was created
elsewhere". Without that wording, the None-cart case would confidently be labeled `none_value`, and
the quick answer would point at the crash line, 3 calls from the real bug. With it, all 4 harder
cases went to Claude at p ≥ 0.95, and all 4 easy ones were answered at p ≥ 0.94.

**Reading the token numbers honestly:**
- `raw_tokens` is what an agent would otherwise read: the traceback plus the full referenced files.
  `returned_tokens` is the compact output TraceRoot prints. The agent reads **68% less** here. These
  test scripts are only 6–25 lines, so that's a floor: raw tokens grow with file size, while the
  output stays about 55–65 tokens.
- On files this small, the **models spend more tokens in total** (25.6k over 8 runs) than the agent
  saves. The benefit is that cheap Haiku and Jev tokens replace your main agent's context, plus the
  root-cause reasoning: in 4/8 cases the fix was in a different function from the crash. The gate
  makes easy errors cost ~1k tokens and ~0.5 s instead of ~5.4k tokens and ~9 s.

Run `python -m unittest discover tests` for the unit tests (33, none of which call a model).

## Limitations

- **The models only see the traceback and the code slices** (the last 3 project frames ±20 lines,
  merged). A cause in a file or function outside those windows can be missed; `--file` helps.
- **Text token counts are estimates** (`len(text) // 4`). Claude and Jev token counts come from
  their APIs.
- **Python tracebacks only** get source context. Other errors are still analyzed, but from the error
  text alone.
- **The evaluation is small:** 8 hand-made test scripts with one clear bug each. Real errors will be
  closer calls for the gate, and the threshold may need retuning.
- **The CLI backend** depends on a logged-in `claude` install, and each call has ~2.5 s of startup.

## Future work

- The **API backend** (`TRACEROOT_CLAUDE_BACKEND=api`) using the `anthropic` SDK. The stub and a
  note on what to implement are in `claude_client._call_api`. Contributions are welcome.
- An MCP server, so agents can call TraceRoot as a tool instead of a shell command
- An auto-run hook that triggers on failed commands
- Parsing non-Python tracebacks (JavaScript, Java, ...)
- A VS Code extension or a hosted website
- Diagrams for every cause, and more test scripts with ambiguous causes to measure Claude/Jev disagreement

## Project files

```
traceroot/      cli, config, trace_parser, jev_client, claude_client, pipeline, store, stats, render_html
tests/          unit tests; fixtures/ = planted-bug scripts, saved tracebacks, run_all.py, gate_report.py
.claude/skills/traceroot/SKILL.md   tells Claude Code when and how to use TraceRoot
LOG.md          dated changelog of every plan, change, and result during the build
```
