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

**What it's for:** cheaper, cleaner debugging, especially for **simple, common errors**. On a
36-bug benchmark ([Results](#results)):
- **Simple errors:** the Jev gate answers alone. That's **65% fewer model tokens** than giving
  Claude every file, the agent reads **52 tokens instead of ~2,100**, and accuracy is the same (11/11).
- **Complex errors:** the agent's context is still **~97% smaller**, at 76% vs. 84% top-1 accuracy
  and ~23% more model tokens than the full-file baseline.

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
- **One-hop definition lookup** (Python's `ast`): adds just the definitions of the project functions,
  classes (header and fields), and constants the failing code uses, even in files that aren't on the
  stack, plus a small second hop. Outer frames follow only the names on the frame line and the local
  assignments feeding them. Everything is capped (40 lines per definition, 160 in total).
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

### Headline

**For simple, common errors, TraceRoot cuts both the model tokens spent and the error text dumped
into the agent's context, with no loss in accuracy.** For complex errors it still keeps the agent's
context ~97% smaller, but it spends *more* model tokens than just handing Claude every file, and it's
a little less accurate.

That distinction matters because the two token pools are different:
- **The agent's context** is the expensive model doing your work. Everything it reads stays there
  and is re-sent on every later turn.
- **TraceRoot's side calls** (Haiku and Jev) are cheap, one-shot, and thrown away after the answer.

### Benchmark: 36 planted bugs in 4 multi-file projects

`bench/` holds 4 clean mini-projects:
- shop: 170 lines
- logs: 357 lines
- gradebook: 401 lines
- planner: 315 lines, **held out**

Each case applies **one known mutation** (a dropped `int()`, a renamed dict key, an off-by-one, a
`None` return, a removed import, a typo, a missing argument, and so on). The mutated line is the
ground truth, stored outside the project so no model ever sees it. Each case runs two ways:

- **TraceRoot:** the real `traceroot analyze --run`
- **Baseline:** the same model (Haiku) and the same prompt, but given the traceback plus **every
  project file in full**, with no gate and no Jev. That's "just ask Claude with everything".

A *hit* is the right file and a line within ±1. Regenerate everything with `python bench/run_bench.py`.
The full per-case table is in [`bench/RESULTS.md`](bench/RESULTS.md).

**Simple vs. complex errors** (simple = the Jev gate answered alone):

| Errors | Cases | TraceRoot top-1 | Baseline top-1 | TraceRoot model tokens | Baseline model tokens | Model tokens | Agent context: baseline → TraceRoot |
|---|---|---|---|---|---|---|---|
| **Simple (gate)** | 11 | **11/11 (100%)** | 11/11 (100%) | **2,966** | 8,412 | **−65%** | **2,100 → 52 (−98%)** |
| Complex (Claude + Jev) | 25 | 19/25 (76%) | 21/25 (84%) | 11,072 | 8,981 | +23% | 1,735 → 59 (−97%) |
| All | 36 | 30/36 (83%) | 32/36 (89%) | 8,595 | 8,807 | −2% | 1,846 → 57 (−97%) |

**Development set vs. held-out set:** projects 1–3 were used to *improve* TraceRoot (see LOG.md).
The planner project was written **after the tool was frozen** and never used for tuning.

| Set | TraceRoot top-1 | TraceRoot top-3 | Baseline top-1 | TraceRoot tokens | Baseline tokens |
|---|---|---|---|---|---|
| Development (27, tuned on) | 22/27 (81%) | 25/27 (93%) | 24/27 (89%) | 8,316 | 8,870 |
| **Held-out (9)** | **8/9 (89%)** | 8/9 (89%) | **8/9 (89%)** | 9,431 | 8,617 |

**Other numbers:**
- **Jev gate:** answered 11/36 cases (31%) alone, and **all 11 were right** (100% precision). The
  gate path averages ~3.0k model tokens and ~1 s, vs. ~11.1k tokens and ~10 s for the full path.
- **By distance from the crash:**

  | Distance | TraceRoot top-1 | Baseline top-1 |
  |---|---|---|
  | Bug on the crash line (9 cases) | 9/9 | 9/9 |
  | Same file, elsewhere (14 cases) | 12/14 | 12/14 |
  | Different file (13 cases) | 9/13 | 11/13 |

- **Does Jev's re-ranking help? No.** On the 25 complex cases, ordering TraceRoot's own candidates by
  Claude's rank would give 21/25 top-1, while Jev's order (what ships) gives 19/25. The gate is where
  Jev pays off; as a scorer it slightly hurts.

### How the benchmark changed TraceRoot

The first version scored **4/9** on the shop project, against the baseline's 9/9. The bug was usually
in code that had *already returned*, such as `load_catalog` parsing a price, so it was never on the
call stack, and TraceRoot only read files in the traceback. The fix is plain code:
**one-hop definition lookup** (Python's `ast`). It adds just the definitions of project functions,
classes, and constants that the failing code uses, plus a small second hop. With it, shop went to 8/9
at about 1k tokens of context. Each iteration (v1 → v4) is recorded in LOG.md.

### Original 8 test scripts

The single-file scripts in `tests/fixtures/` (`python tests/fixtures/run_all.py`) all score 8/8, but
they're tiny and the cause is always inside the code window. The benchmark above is the meaningful
measure.

**Unit tests:** `python -m unittest discover tests` runs 41 tests, none of which call a model. They
cover parsing, safety rules, definition lookup, validation, ranking, the gate decision, stats, the
HTML view, and the benchmark's own scoring.

## Limitations

- **Complex errors cost more model tokens than "send everything"** on projects of this size
  (~11k vs. ~9k), mostly because Jev's two calls each carry the code. The saving there is in the
  agent's context, not in total spend.
- **Jev's re-ranking slightly hurts** (19/25 vs. 21/25 with Claude's own order). Ranking by Claude,
  or sending Jev less code, are the obvious next experiments.
- **The models only see the traceback and the selected code**: the last 3 project frames ±20 lines,
  plus one-hop definitions. Causes reached only through object methods (`course.find_student`) or
  through more than two hops can be missed (4 of the 6 TraceRoot misses). `--file` helps.
- **Benchmark caveats:**
  - It's 36 cases, each run once, and model answers vary between runs.
  - The projects and mutations were written by the same model family the tool uses.
  - Only the held-out project (9 cases) was never tuned on.
- **Text token counts are estimates** (`len(text) // 4`). Claude and Jev token counts come from
  their APIs.
- **Python tracebacks only** get source context. Other errors are still analyzed, but from the error
  text alone.
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
bench/          benchmark: projects/ (4 clean apps), cases.py (36 mutations), run_bench.py, RESULTS.md
.claude/skills/traceroot/SKILL.md   tells Claude Code when and how to use TraceRoot
LOG.md          dated changelog of every plan, change, and result during the build
```
