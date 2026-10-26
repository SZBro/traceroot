# TraceRoot

**Trace an error back to its root cause, with fewer agent tokens.**

TraceRoot is a local Python CLI that you, or a coding agent like Claude Code, run on a failing
command. A coding agent would normally read a long traceback and open several files. TraceRoot
returns a compact, ranked root cause instead, one at a time:

```console
$ traceroot analyze --run "python tests/fixtures/medium_none_cart.py"
[1/4] none_value (claude=0.60, Jev agrees) tests/fixtures/medium_none_cart.py:5
cause: load_cart replaces empty item list with None
fix: Keep items as an empty list (for example, default to [] instead of None) rather than converting falsy values to None.
more: `traceroot next`

$ traceroot next
[2/4] none_value (claude=0.20, jev=0.01) tests/fixtures/medium_none_cart.py:11
cause: price_items does not guard against None items
fix: Add a guard such as items = items or [] before the comprehension, or check for None explicitly.
more: `traceroot next`
```

The crash in that example happens in `price_items` (line 11), three calls away. TraceRoot points
at `load_cart` (line 5), where the bad value is created. That function isn't in the traceback at all.

**What it's for:** cheaper, cleaner debugging. On a 54-bug benchmark ([Results](#results)):
- **Same accuracy as giving Claude every file** (47/54 top-1), with **18% fewer model tokens** and the
  agent reading **~62 tokens instead of ~1,800** (−97%).
- **Simple, common errors:** the Jev gate answers alone. That's **76% fewer model tokens**, 18/18 correct.
- **Scope:** Python tracebacks. Other languages fall back to text-only analysis, with no code context.

Commands: `traceroot` or the short alias `trt` (not `tr`, which is a standard Unix command).

**Contents:** [How it works](#how-it-works) · [Responsibilities](#responsibilities-what-each-part-does) ·
[Install](#install) · [Usage](#usage) · [Backends](#claude-backends-claude--p-vs-the-api) ·
[Results](#results) · [Limitations](#limitations) · [Future work](#future-work) ·
[Build log](LOG.md)

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
  assignments feeding them. `obj.method()` calls are followed when exactly one project class defines
  that method. Everything is capped (40 lines per definition, 160 in total).
- **Fuzzy file paths:** if Claude cites a file that doesn't exist, but exactly one safe project file has
  that name, the citation is mapped to it. Blocked files like `.env` can never match.
- **Validating Claude's output:**
  - drops candidates without a title and renames duplicate ids
  - clears any file that doesn't exist or isn't allowed, plus its line (so Claude can't cite `.env`
    or an invented file)
  - discards probabilities outside 0–1
  - maps unknown categories to `other_or_complex`
  - caps the list at 6
- **Validating Jev's output:** rejects scores whose options don't match the candidates. Malformed
  diagrams are rejected, and model text is HTML-escaped in the view.
- **Ranking and decisions:** applies the gate threshold, orders causes by Claude's rank, and records
  whether Jev agrees with #1. Without Jev, it simply skips the agreement check.
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
git clone https://github.com/SZBro/traceroot.git
cd traceroot
python -m venv .venv
source .venv/Scripts/activate   # Windows (Git Bash). macOS/Linux: source .venv/bin/activate
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

**TraceRoot v6 matches the accuracy of giving Claude every file (47/54 top-1 on a 54-bug benchmark),
while spending 18% fewer model tokens and putting 97% less error text into the agent's context.** For
**simple, common errors**, the Jev gate answers alone with **76% fewer model tokens, 18/18 correct**.

The two token pools are different:
- **The agent's context** is the expensive model doing your work. Everything it reads stays there
  and is re-sent on every later turn.
- **TraceRoot's side calls** (Haiku and Jev) are cheap, one-shot, and thrown away after the answer.

### Benchmark: 54 planted bugs in 6 multi-file projects

`bench/` holds 6 clean mini-projects (170–401 lines each): shop, logs, gradebook, planner, library,
and **bank (held out)**. Each case applies **one known mutation** (a dropped `int()`, a renamed dict
key, an off-by-one, a `None` return, a removed import, a typo, a missing argument, a lookup that
returns `None`, and so on). The mutated line is the ground truth, stored outside the project so no
model ever sees it. Each case runs two ways:

- **TraceRoot:** the real `traceroot analyze --run`
- **Baseline:** the same model (Haiku) and the same prompt, but given the traceback plus **every
  project file in full**, with no gate and no Jev. That's "just ask Claude with everything".

A *hit* is the right file and a line within ±1. Regenerate everything with `python bench/run_bench.py`,
and compare versions with `python bench/compare.py A.jsonl B.jsonl`. Per-case tables are in
[`bench/RESULTS.md`](bench/RESULTS.md), and every version's raw results are in `bench/versions/`.

**Final version (v6), simple vs. complex errors** (simple = the Jev gate answered alone):

| Errors | Cases | TraceRoot top-1 | Baseline top-1 | TraceRoot model tokens | Baseline model tokens | Model tokens | Agent context: baseline → TraceRoot |
|---|---|---|---|---|---|---|---|
| **Simple (gate)** | 18 | **18/18 (100%)** | 17/18 (94%) | **1,968** | 8,202 | **−76%** | **1,922 → 51 (−97%)** |
| Complex (Claude + Jev) | 36 | 29/36 (81%) | 30/36 (83%) | 9,577 | 8,830 | +8% | 1,719 → 68 (−96%) |
| **All** | 54 | **47/54 (87%)** | 47/54 (87%) | **7,040** | 8,621 | **−18%** | 1,787 → 62 (−97%) |

**Development vs. held-out.** Projects 1–5 were used to improve TraceRoot (v1 → v6; see LOG.md).
The bank project was **written and committed before the v6 code** (git `4887e17`) and is the fair
test of v6:

| Set | TraceRoot v6 top-1 | top-3 | Baseline top-1 | top-3 | TraceRoot tokens | Baseline tokens |
|---|---|---|---|---|---|---|
| Development (45, tuned on) | 41/45 (91%) | 42/45 | 41/45 (91%) | 44/45 | 7,135 | 8,711 |
| **Held-out bank (9)** | **6/9** | **9/9** | 6/9 | 8/9 | **6,568** | 8,171 |

**Other numbers:**
- **Jev gate:** answered 18/54 (33%) alone, and **all 18 were right**. It costs ~2.0k model tokens and
  ~1 s, vs. ~9.6k tokens and ~10 s on the full path.
- **By distance from the crash:** TraceRoot and the baseline tie in every bucket (crash line 14/14,
  same file 18/22, different file 15/18).
- **Jev's role:** ordering by Jev's score would get 28/36 top-1 on complex cases, vs. 29/36 with
  Claude's order (what ships). So Jev is a **second opinion**: the output says "Jev agrees" or "Jev
  prefers #k", and shows Jev's pick on an `alt:` line when they disagree.

### Improvement experiments: v4 → v5 → v6

Every change went behind a setting and was **kept only if it didn't make the numbers worse**, checked
on a project written *before* the change ([LOG.md](LOG.md) has every step):

| Version | Change | Result | Kept? |
|---|---|---|---|
| v5 | A. Wider gate (threshold 0.8 → 0.65) | let **one wrong quick answer** through | **No, reverted** |
| v5 | C. Rank by Claude, Jev as agreement check | +3 cases at rank 1; Jev-only order is worse | Yes |
| v5 | D. Jev sees only crash windows | −0.9k tokens (simple), −1.6k (complex) | Yes |
| v6 | F. Follow `obj.method()` to the one class defining it | +4 top-1 on dev; held-out bank-03 miss → rank 2; +48 context tokens | Yes |
| v6 | P. Fuzzy file paths (unique file-name match) | rescued shop-01 (right cause, wrong path) | Yes |

| Totals | v4 | v5 | **v6** | Baseline |
|---|---|---|---|---|
| Top-1, 45 dev cases | 35 | 37 | **41** | 41 |
| Avg model tokens | 8,361 | 7,143 | **7,135** | 8,711 |

Two lessons from the experiments:
- **A and D interacted.** The leaner context made Jev more confident on a case that only looks local,
  and the lower threshold let it through.
- **Single runs are noisy.** On held-out bank, one case (bank-08) dropped from rank 1 to 2 between v5
  and v6 even though Claude received *identical* context. That's model variance, not a v6 effect.

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

**Unit tests:** `python -m unittest discover tests` runs 47 tests, none of which call a model. They
cover parsing, safety rules, definition lookup, validation, ranking and the agreement check, the gate
decision, stats, the HTML view, and the benchmark's own scoring.

## Limitations

- **Complex errors cost a bit more model tokens** than "send everything" on projects of this size
  (~9.6k vs. ~8.8k, +8%). The saving there is in the agent's context (−96%), not in total spend. On
  larger projects the baseline grows with every file, while TraceRoot's context stays about flat.
- **The models only see the traceback and the selected code**: the last 3 project frames ±20 lines,
  plus definitions one or two hops away, plus `obj.method()` calls when exactly one project class
  defines the method. Causes that flow through **object attributes** (`self.books[isbn].copies`, set in
  another file) or through ambiguous method names are still missed. That covers most of the
  remaining misses.
- **Heuristics, not types:** method-following and fuzzy paths only act when a name is *unique* in the
  project. In a large codebase with many `get`/`add` methods, method-following will often stay silent.
- **Benchmark caveats:**
  - It's 54 cases, each run once, and model answers vary between runs (e.g. bank-08 changed rank
    with identical input).
  - The projects and mutations were written by the same model family the tool uses.
  - Only the 9 bank cases were never tuned on, and on them TraceRoot and the baseline tie on top-1 (6/9).
- **Text token counts are estimates** (`len(text) // 4`). Claude and Jev token counts come from
  their APIs.
- **Python tracebacks only** get source context. Other errors are still analyzed, but from the error
  text alone.
- **The CLI backend** depends on a logged-in `claude` install, and each call has ~2.5 s of startup.

## Future work

- The **API backend** (`TRACEROOT_CLAUDE_BACKEND=api`) using the `anthropic` SDK. The stub and a
  note on what to implement are in `claude_client._call_api`. Contributions are welcome.
- **Follow attribute data flow:** for `obj.field` crashes, find where `field` is *assigned* (e.g. the
  constructor call in another file). Methods are followed since v6; attributes are not.
- **3-way gate:** add a second Jev question in the same request ("is the cause probably in another
  file?") and switch to full-file mode for those cases.
- **Cut Jev tokens further:** shorter category descriptions (~300 of the ~1,000 tokens per gate call),
  or skip Jev's second opinion when Claude is already confident.
- **Repeat runs** of the benchmark to measure model variance, plus a larger, real-world bug set
  (e.g. BugsInPy).
- An MCP server, so agents can call TraceRoot as a tool instead of a shell command
- An auto-run hook that triggers on failed commands
- Parsing non-Python tracebacks (JavaScript, Java, ...)
- A VS Code extension
- Diagrams for every cause, and more test scripts with ambiguous causes to measure Claude/Jev disagreement

## Project files

```
traceroot/      cli, config, trace_parser, jev_client, claude_client, pipeline, store, stats, render_html
tests/          unit tests; fixtures/ = planted-bug scripts, saved tracebacks, run_all.py, gate_report.py
bench/          benchmark: projects/ (6 clean apps), cases.py (54 mutations), run_bench.py, compare.py,
                RESULTS.md, versions/ (raw results of v4, v5a, v5, v6)
.claude/skills/traceroot/SKILL.md   tells Claude Code when and how to use TraceRoot
LOG.md          dated changelog of every plan, change, and result during the build
```
