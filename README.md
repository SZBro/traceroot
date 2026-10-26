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

**What it's for:** cheaper, cleaner debugging for coding agents. On a 54-bug benchmark it finds
the root cause **as accurately as giving Claude every file (47/54)**, with **18% fewer model tokens**
and **97% less error text in the agent's context**. Simple errors take **0.7 s instead of 8.2 s** with
76% fewer tokens. See [Why use it](#why-use-it-the-advantages-measured). Python tracebacks only, for now.

Commands: `traceroot` or the short alias `trt` (not `tr`, which is a standard Unix command).

**Results website:** [szbro.github.io/traceroot](https://szbro.github.io/traceroot/), with charts and screenshots.

**Contents:** [Why use it](#why-use-it-the-advantages-measured) ·
[**Set it up for your coding agent**](#set-it-up-for-your-coding-agent) ·
[How it works](#how-it-works) · [Responsibilities](#responsibilities-what-each-part-does) ·
[Developer install](#developer-install) · [Usage](#usage) · [Backends](#claude-backends-claude--p-vs-the-api) ·
[Results](#results) · [Limitations](#limitations) · [Future work](#future-work) ·
[Build log](LOG.md)

---

## Why use it: the advantages, measured

Every number below comes from the benchmark in this repo: **54 planted bugs in 6 multi-file Python
projects**. TraceRoot is compared with the same Claude model (Haiku) given the traceback plus **every
project file in full**, i.e. "just ask Claude with everything". The raw data is in
[`bench/versions/v6_results.jsonl`](bench/versions/v6_results.jsonl), and the details are in
[Results](#results).

| | **TraceRoot** | Claude + every file | Difference |
|---|---|---|---|
| Error text left in the agent's context, per bug | **62 tokens** | 1,787 (traceback + its files), 2,485 (whole project) | **−97% / −98%** |
| Correct #1 root cause, all 54 bugs | **47/54 (87%)** | 47/54 (87%) | **same** |
| Model tokens per bug, all 54 bugs | **7,040** | 8,621 | **−18%** |
| Time per bug, all 54 bugs | **7.6 s** | 9.3 s | **−18%** |
| **Simple errors** (18 bugs): correct #1 cause | **18/18** | 17/18 | +1 |
| **Simple errors**: model tokens | **1,968** | 8,202 | **−76%** |
| **Simple errors**: time to answer | **0.7 s** | 8.2 s | **~12× faster** |
| Next-best cause if #1 is wrong (`traceroot next`) | **0 tokens** (saved list) | a new model call | free |

**1. It keeps the agent's context clean.** Instead of a traceback and several source files
(~1,800–2,500 tokens), the agent reads a ~62-token answer: category, `file:line`, cause, and fix.
That matters because everything an agent reads stays in its context and is re-sent on every later
turn.

**2. Simple errors become almost free.** Jev's gate answered **18 of 54 bugs (33%) by itself**:
missing imports, typos, wrong arguments, off-by-ones on the crash line. **All 18 were right**, at
~2k tokens and **0.7 s each, with no Claude call at all.**

**3. Same accuracy as "send everything", from a fraction of the code.** Claude sees only the crash
windows plus the definitions the failing code actually uses (about 1.4k tokens of code), and still
names the exact buggy line as often as when it sees every file: 47/54 each.

**4. It finds root causes that aren't on the call stack.** In 18 of the bugs, the mistake was in a
*different file* from the crash (a value parsed wrong in `catalog.py`, crashing later in `pricing.py`).
TraceRoot found 15/18, the same as the baseline, because it follows the functions and constants the
failing code uses, even after they've returned.

**5. Its cost stays flat as projects grow; "send everything" doesn't.**

| Project (lines of Python) | Claude + every file | TraceRoot's Claude call | TraceRoot, average per bug |
|---|---|---|---|
| shop (170) | 6,462 | 5,177 | 7,455 |
| bank (277) | 8,171 | 5,223 | 6,568 |
| library (291) | 8,327 | 5,957 | 6,812 |
| planner (315) | 8,617 | 6,223 | 7,170 |
| logs (357) | 8,924 | 5,449 | 6,998 |
| gradebook (401) | **11,224** | 5,683 | 7,239 |

The baseline grew **74%** from the smallest project to the largest, while TraceRoot's Claude call
stayed at about 5.2–6.2k. These projects are small. Real codebases have thousands of lines, where
sending every file isn't even possible.

**6. It's safe by construction.** Plain code decides what the models see. It never reads `.env`,
`*.key`, `*.pem`, `.git/`, or installed packages, and it checks every `file:line` the model cites
against real project files. Unit tests cover all of these rules (52 tests, no model calls).

**Where it doesn't help (yet):**
- On **complex errors in small projects**, TraceRoot spends ~8% *more* model tokens than "send
  everything" (9,577 vs. 8,830) and is 1 case less accurate (29/36 vs. 30/36).
- In a one-off **end-to-end agent trial** on the 170-line shop project, the agent used *more* total
  tokens with TraceRoot (246k vs. 207k), because extra agent turns cost more than the file reading
  saved. See [the agent trial](#does-it-actually-help-an-agent-one-real-trial-honestly).
- It only gives code context for **Python** tracebacks.

## Set it up for your coding agent

TraceRoot is built to be used **by coding agents**. A human can run the same commands, but the goal is
that your agent calls `traceroot` on its own whenever a Python command fails, instead of reading the
whole traceback and opening files. Setup takes about 5 minutes and works for every project on your
machine.

### What you need

- **Python 3.10+**
- **Claude Code, installed and logged in.** TraceRoot calls Claude through the `claude` command
  (`claude -p`), so no Anthropic API key is needed. Check it with `claude --version`. If `claude`
  isn't found, install it from [claude.com/claude-code](https://claude.com/claude-code), run `claude`
  once to log in, and make sure its folder is on your `PATH`.
- **A TypeSafe API key** for Jev (from your TypeSafe console). This is optional: without it,
  TraceRoot still works, but there's no Jev gate and no second opinion.

### Step 1: Install the `traceroot` command so every project can use it

The command has to be on your `PATH` in *any* folder, because your agent runs it from inside your
own projects.

```bash
# Recommended: an isolated install that's on PATH everywhere
pipx install git+https://github.com/SZBro/traceroot.git

# Or, without pipx
pip install --user git+https://github.com/SZBro/traceroot.git
```

Then check that it worked:

```bash
traceroot --help
```

(`trt` is the same command, shorter.) If you'd rather work from a clone, see
[Developer install](#developer-install). In that case the agent's shell must have that venv's
`Scripts/` (Windows) or `bin/` folder on its `PATH`.

### Step 2: Put your Jev key in your user config

The user config at `~/.traceroot/.env` is read no matter which project you're in. Settings are read
in this order, and the first one found wins:
1. real environment variables
2. `./.env` in the folder you run from
3. `~/.traceroot/.env`

```bash
mkdir -p ~/.traceroot
echo "TYPESAFE_API_KEY=your-key-here" >> ~/.traceroot/.env
```

On Windows, `~` is `C:\Users\<you>`. The key is never printed, logged, or sent anywhere except
TypeSafe's API. Other settings you can put here are listed in [Settings](#settings).

### Step 3: Install the Claude Code skill

The skill is a short instruction file that tells Claude Code when and how to use TraceRoot.

```bash
traceroot install-skill            # for ALL your projects: ~/.claude/skills/traceroot/SKILL.md
traceroot install-skill --project  # for just this project:  ./.claude/skills/traceroot/SKILL.md
```

Use `--project` and commit the file if you want your whole team's Claude Code to use TraceRoot in that
repo. **Restart Claude Code** (or start a new session) afterwards so it loads the skill.

### Step 4 (optional): Let the agent run TraceRoot without permission prompts

In your project's `.claude/settings.json` (or `~/.claude/settings.json` for all projects):

```json
{
  "permissions": {
    "allow": ["Bash(traceroot:*)", "Bash(trt:*)"]
  }
}
```

### Step 5: Ignore TraceRoot's state folder in each project

TraceRoot keeps its last result and run stats in `.traceroot/` at the project root. Add it to the
project's `.gitignore`:

```bash
echo ".traceroot/" >> .gitignore
```

### Step 6: Check that everything is set up

```bash
traceroot check          # claude found? Jev key set? parser OK? skill installed? (free, no model calls)
traceroot check --live   # also makes one tiny Claude call
```

Expected output:

```text
[ok] claude CLI: C:\Users\you\.local\bin\claude.exe
[ok] TYPESAFE_API_KEY: set  (looked in env, ./.env, C:\Users\you\.traceroot\.env)
[ok] traceback parser
[info] project root: C:\path\to\your\project  (state in C:\path\to\your\project\.traceroot)
[ok] user skill: C:\Users\you\.claude\skills\traceroot\SKILL.md
```

Then try it for real. Open Claude Code in a Python project and ask: *"`python main.py` is failing,
find the root cause and fix it."* You should see the agent run
`traceroot analyze --run "python main.py"` before it opens any files.

### What the agent does with it

A real answer from the benchmark (case shop-04, where the crash is in `cart.py` and the bug is in
`catalog.py`):

```text
agent: traceroot analyze --run "python main.py"
       [1/4] none_value (claude=0.45, Jev prefers #4) shop/catalog.py:31
       cause: find_product lowercases lookup key but catalog keys keep case
       fix: Normalize SKUs the same way in both load_catalog and find_product, for example by storing keys as sku.strip().lower().
       alt (Jev's pick, #4): build_cart does not handle a missing product main.py:14
       more: `traceroot next`
agent: (opens shop/catalog.py near line 31, applies the fix, reruns)
       ...if that wasn't it:  traceroot next   (free, no model call)
```

That's 5 lines for the agent to read instead of the traceback plus 3 files. Jev disagreed here, so
the agent also sees the strongest alternative.

### Other agents (Codex, Cursor, Aider, Copilot, ...)

Agents without Claude Code skills can follow the same rules from their instruction file, such as
`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, or `.github/copilot-instructions.md`. Paste this in:

```markdown
## Debugging Python errors
When a Python command fails with a traceback, run `traceroot analyze --run "<command>"` from the
project root BEFORE reading the full traceback or opening files. Act on the top cause (open only the
file:line it names). If it's wrong, run `traceroot next` (free). If it prints "no more candidates",
debug normally. Add `--json` for the full explanation.
```

TraceRoot still calls Claude through `claude -p` under the hood, so Claude Code must be installed and
logged in, even if your agent is a different product.

### Does it actually help an agent? (one real trial, honestly)

`bench/agent_trial.py` runs **headless Claude Code (Haiku)** on a fresh copy of a buggy project, twice:
once with the skill installed, and once without it. On case shop-01 (the price is never converted;
the crash is in another file):

| | With TraceRoot skill | Without |
|---|---|---|
| The agent found and used TraceRoot on its own | **yes**: it loaded the skill, then ran `traceroot analyze --run` | – |
| Fixed the right line | yes | yes |
| Agent turns / total agent tokens | 9 / ~246k | 6 / ~207k |

**The setup works**: an unmodified agent discovered the skill and used TraceRoot. But on this
**tiny** project (170 lines), it didn't reduce the agent's total tokens. Each extra agent turn re-sends
the agent's own system prompt (~20k tokens), and that outweighs the file reading TraceRoot saves when
the agent could just print all 5 files at once. A second trial with reworded skill instructions came
out worse (346k): the agent ran the command and read files first anyway. That wording was reverted.

The token savings measured in [Results](#results) are for the *debugging step itself* (what has to
be read to find the cause). They should matter more on real projects, where "just read every file"
isn't an option. A proper multi-case agent benchmark is listed under Future work.

### Using it yourself (humans)

The same commands work by hand: `traceroot analyze --run "python app.py"`, then `traceroot next`.
`traceroot view` opens a local HTML page with all causes ranked and a diagram of the call path.

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

## Developer install

To work on TraceRoot itself, or run the benchmark, clone it. Requires Python 3.10+ and [Claude Code](https://claude.com/claude-code) (the `claude` command,
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

`.env` is git-ignored and never printed.

### Settings

These go in `.env` or `~/.traceroot/.env`:

| Variable | Default | Meaning |
|---|---|---|
| `TYPESAFE_API_KEY` | (none) | Jev key. Without it TraceRoot still works, ranking by Claude only. |
| `TRACEROOT_CLAUDE_BACKEND` | `cli` | How Claude is called (only `cli` exists today). |
| `TRACEROOT_CLAUDE_MODEL` | `claude-haiku-5-5` | Model for candidates and diagrams. |
| `TRACEROOT_CLAUDE_BIN` | (auto) | Path to `claude` if it isn't on PATH. |
| `GATE_THRESHOLD` | `0.8` | Minimum Jev probability for a gate-only answer. |
| `TRACEROOT_RANK_BY` | `claude` | `claude` (Jev = second opinion) or `jev` (v4 behavior). |
| `TRACEROOT_JEV_CONTEXT` | `windows` | What code Jev sees: `windows` or `all`. |
| `TRACEROOT_FOLLOW_METHODS` / `TRACEROOT_FUZZY_PATHS` | `1` | v6 features; `0` turns them off. |
| `TRACEROOT_CONFIG` | `~/.traceroot/.env` | Path to the user config file. |

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
traceroot install-skill [--project]   # install the Claude Code skill
traceroot check [--live]              # verify the setup
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

**Unit tests:** `python -m unittest discover tests` runs 52 tests, none of which call a model. They
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
- **An agent-level benchmark:** many cases × several runs of `bench/agent_trial.py` on larger
  projects, to measure end-to-end agent tokens with and without TraceRoot.
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
