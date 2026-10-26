---
name: traceroot
description: Use when a Python command fails with a traceback or error. Run `traceroot analyze` first to get a compact, ranked root cause instead of reading the whole traceback and opening files.
---

# TraceRoot

When a Python command fails with a traceback, run TraceRoot **before** reading the traceback in full or
opening source files. Run it from the project root:

```bash
traceroot analyze --run "<the failing command>"
```

If you already have the error text, pipe it in instead: `<command> 2>&1 | traceroot analyze`.

The output is a few lines: the category, scores, `file:line`, the cause, and a fix. Sometimes an `alt:`
line shows a second candidate.

1. Act on the top cause: open only the file and line it names, and apply the fix. If an `alt:` line
   is shown, consider that cause too.
2. If that cause turns out to be wrong, run `traceroot next` for the next-ranked cause. It makes no
   model call, so it's free.
3. When it prints "no more candidates", fall back to reading the traceback yourself, or rerun with
   `--file <path>` to include a file the traceback doesn't show.

Use `traceroot view` only when the user asks for a visual (it opens an HTML page with a diagram).
Add `--json` if you need the full explanation for a cause.

If `traceroot` is not found, tell the user to install it (see the TraceRoot README). Don't work around
it. TraceRoot only gives code context for Python tracebacks; for other languages, debug as usual.
