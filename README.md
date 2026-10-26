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
45-bug benchmark ([Results](#results)):
- **Simple errors:** the Jev gate answers alone. That's **76% fewer model tokens** than giving
  Claude every file, the agent reads **51 tokens instead of ~2,050**, and accuracy is the same (15/15).
- **Complex errors:** the agent's context is still **~96% smaller**, but accuracy is lower than the
  full-file baseline (73% vs. 87%; 2/5 on the held-out project), at ~9% more model tokens.

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
2. **Second opinion:** on the full path, Jev independently scores Claude's candidates (one
   probability each) and decides whether it **agrees** with Claude's #1. If it doesn't, Jev's pick is
   shown to the agent as an `alt:` line. Since v5 the order is Claude's: the benchmark showed Jev's
   order was worse (18/30 vs. 22/30). Setting `TRACEROOT_RANK_BY=jev` restores v4 behavior.

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

**For simple, common errors, TraceRoot cuts model tokens by ~76% and the error text dumped into the
agent's context by ~98%, with the same accuracy as giving Claude every file (15/15).** For complex
errors, it still keeps the agent's context ~96% smaller, but it's less accurate than the
full-file baseline (73% vs. 87%) and spends ~9% more model tokens.

The two token pools are different:
- **The agent's context** is the expensive model doing your work. Everything it reads stays there
  and is re-sent on every later turn.
- **TraceRoot's side calls** (Haiku and Jev) are cheap, one-shot, and thrown away after the answer.

### Benchmark: 45 planted bugs in 5 multi-file projects

`bench/` holds 5 clean mini-projects:
- shop: 170 lines
- logs: 357 lines
- gradebook: 401 lines
- planner: 315 lines
- library: 291 lines, **held out**

Each case applies **one known mutation** (a dropped `int()`, a renamed dict key, an off-by-one, a
`None` return, a removed import, a typo, a missing argument, and so on). The mutated line is the
ground truth, stored outside the project so no model ever sees it. Each case runs two ways:

- **TraceRoot:** the real `traceroot analyze --run`
- **Baseline:** the same model (Haiku) and the same prompt, but given the traceback plus **every
  project file in full**, with no gate and no Jev. That's "just ask Claude with everything".

A *hit* is the right file and a line within ±1. Regenerate everything with `python bench/run_bench.py`.
Per-case tables are in [`bench/RESULTS.md`](bench/RESULTS.md), and every version's raw results are in
`bench/versions/`.

**Final version (v5), simple vs. complex errors** (simple = the Jev gate answered alone):

| Errors | Cases | TraceRoot top-1 | Baseline top-1 | TraceRoot model tokens | Baseline model tokens | Model tokens | Agent context: baseline → TraceRoot |
|---|---|---|---|---|---|---|---|
| **Simple (gate)** | 15 | **15/15 (100%)** | 15/15 (100%) | **2,019** | 8,309 | **−76%** | **2,051 → 51 (−98%)** |
| Complex (Claude + Jev) | 30 | 22/30 (73%) | 26/30 (87%) | 9,705 | 8,912 | +9% | 1,736 → 65 (−96%) |
| All | 45 | 37/45 (82%) | 41/45 (91%) | **7,143** | 8,711 | **−18%** | 1,841 → 61 (−97%) |

**Development vs. held-out:** projects 1–4 were used to improve TraceRoot (v1 → v5; see LOG.md). The
library project was written **after the last change** and is the only fair test of v5:

| Set | TraceRoot v5 top-1 | Baseline top-1 | TraceRoot tokens | Baseline tokens |
|---|---|---|---|---|
| Development (36, tuned on) | 31/36 (86%) | 32/36 (89%) | 7,255 | 8,807 |
| **Held-out (9)** | **6/9 (67%)**: simple 4/4, complex 2/5 | **9/9** | 6,693 | 8,327 |

The held-out set shows the real weak spot. All 3 complex misses involve data flowing through
**object attributes or methods** (`self.books[isbn].copies`, `directory.find(...)`,
`self.joined`), which the definition lookup doesn't follow. The baseline sees every file, so it
doesn't have that problem.

**Other numbers:**
- **Jev gate:** answered 15/45 (33%) alone, and **all 15 were right**. It costs ~2.0k model tokens and
  ~1 s, vs. ~9.7k tokens and ~10 s on the full path.
- **Jev as a re-ranker vs. as a second opinion:** on the 30 complex cases, ordering by Jev's score
  would get 18/30 top-1, while Claude's own order (what v5 ships) gets 22/30. So v5 uses Jev as an
  **agreement check**. The output says "Jev agrees" or "Jev prefers #k", and shows Jev's pick on an
  `alt:` line when the two disagree.

### Improvement experiment: v4 → v5

Three changes, each behind a setting and kept only if the numbers didn't get worse (LOG.md, 21:04–21:20):

| Change | Result | Kept? |
|---|---|---|
| A. Wider gate (threshold 0.8 → 0.65) | let **one wrong quick answer** through (gate precision 11/12) | **No, reverted** |
| C. Rank by Claude, Jev as agreement check | 3 cases moved up to rank 1; Jev-only order is worse | **Yes** |
| D. Jev sees only crash windows, not extra definitions | −0.9k tokens on simple errors, −1.6k on complex | **Yes** |

A and D *interacted*: the leaner context made Jev more confident on a case that only looks local,
and the lower threshold let it through. That's why they had to be judged together.

| All 45 cases | v4 | **v5** | Baseline |
|---|---|---|---|
| Top-1 | 35/45 | **37/45** | 41/45 |
| Gate answers correct | 15/15 | **15/15** | – |
| Avg model tokens | 8,361 | **7,143 (−15%)** | 8,711 |
| Simple-error tokens | ~2,950 | **~2,020** | ~8,300 |
| Held-out library top-1 | 5/9 | **6/9** | 9/9 |

### How the benchmark changed TraceRoot (v1 → v4)

The first version scored **4/9** on the shop project, against the baseline's 9/9. The bug was usually
in code that had *already returned*, such as `load_catalog` parsing a price, so it was never on the
call stack, and TraceRoot only read files in the traceback. The fix is plain code:
**one-hop definition lookup** (Python's `ast`). It adds just the definitions of project functions,
classes, and constants that the failing code uses, plus a small second hop. With it, shop went to 8/9
at about 1k tokens of context.

### Original 8 test scripts

The single-file scripts in `tests/fixtures/` (`python tests/fixtures/run_all.py`) all score 8/8, but
they're tiny and the cause is always inside the code window. The benchmark above is the meaningful
measure.

**Unit tests:** `python -m unittest discover tests` runs 45 tests, none of which call a model. They
cover parsing, safety rules, definition lookup, validation, ranking and the agreement check, the gate
decision, stats, the HTML view, and the benchmark's own scoring.

## Limitations

- **Complex errors are TraceRoot's weak spot:** 73% top-1 vs. 87% for the full-file baseline, and
  only **2/5 on the held-out project**, at ~9% more model tokens (~9.7k vs. ~8.9k). The saving
  there is in the agent's context (−96%), not in accuracy or total spend. For hard bugs, reading the
  files (or `--file`) is still the safer option.
- **The models only see the traceback and the selected code**: the last 3 project frames ±20 lines,
  plus one-hop definitions. Causes reached through **object attributes or methods**
  (`self.books[isbn].copies`, `directory.find(...)`) or through more than two hops are missed. That
  accounts for most of TraceRoot's misses, including all 3 complex misses on the held-out set.
- **Strict file matching:** in one case (shop-01, v5) Claude named the right cause, but its file path
  didn't validate and was dropped, so the case counts as a miss.
- **Benchmark caveats:**
  - It's 45 cases, each run once, and model answers vary between runs (shop-01 flipped from hit to
    miss between v4 and v5 with no related change).
  - The projects and mutations were written by the same model family the tool uses.
  - Only the 9 library cases were never tuned on.
- **Text token counts are estimates** (`len(text) // 4`). Claude and Jev token counts come from
  their APIs.
- **Python tracebacks only** get source context. Other errors are still analyzed, but from the error
  text alone.
- **The CLI backend** depends on a logged-in `claude` install, and each call has ~2.5 s of startup.

## Future work

- The **API backend** (`TRACEROOT_CLAUDE_BACKEND=api`) using the `anthropic` SDK. The stub and a
  note on what to implement are in `claude_client._call_api`. Contributions are welcome.
- **Follow object attributes and methods** in the definition lookup, e.g. resolve `directory.find`
  when exactly one project class defines `find`. This targets most of the remaining misses.
- **3-way gate:** add a second Jev question in the same request ("is the cause probably in another
  file?") and switch to full-file mode for those cases, where the baseline wins.
- Fuzzy path matching when Claude's cited file is close to a real project file (the shop-01 case).
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
