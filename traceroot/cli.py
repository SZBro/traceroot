"""TraceRoot CLI: traceroot / trt  (analyze | next | view | stats)."""
import argparse
import json
import sys
from pathlib import Path

from . import config, pipeline, store, trace_parser

NO_MORE = "no more candidates; try `traceroot analyze` with `--file`"


def _read_input(args) -> str | None:
    if args.run:
        code, err = trace_parser.run_command(args.run)
        if code == 0:
            print(f"traceroot: `{args.run}` exited 0; nothing to analyze")
            return None
        return err
    if args.source:
        p = Path(args.source)
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else args.source
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return None


def cmd_analyze(args) -> int:
    text = _read_input(args)
    if text is None:
        if not args.run:
            print("traceroot: give an error: --run \"cmd\", a traceback file, text, or pipe it in")
        return 1 if not args.run else 0
    if not text.strip():
        print("traceroot: the command failed but printed nothing to stderr")
        return 1
    result = pipeline.analyze(text, extra_file=args.file)
    return _show(result["causes"][0], 0, len(result["causes"]), args.json)


def cmd_next(args) -> int:
    if store.load() is None:
        print("traceroot: nothing saved yet; run `traceroot analyze` first")
        return 1
    step = store.advance()
    if step is None:
        print(NO_MORE)
        return 0
    cause, idx, total = step
    return _show(cause, idx, total, args.json)


def _show(cause: dict, idx: int, total: int, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"index": idx + 1, "total": total, **cause}, indent=2))
    else:
        print(pipeline.format_cause(cause, idx, total))
    return 0


def cmd_view(args) -> int:
    print("traceroot: `view` arrives in build step 6")
    return 0


def cmd_stats(args) -> int:
    print("traceroot: `stats` arrives in build step 5")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(prog="traceroot", description="Trace an error back to its root cause.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="analyze an error and print the top cause")
    a.add_argument("source", nargs="?", help="file containing the traceback, or the error text itself")
    a.add_argument("--run", metavar="CMD", help="run CMD and analyze what it prints to stderr")
    a.add_argument("--file", metavar="PATH", help="also send this project file (for errors with no traceback)")
    a.add_argument("--json", action="store_true", help="print JSON instead of compact text")
    a.set_defaults(func=cmd_analyze)

    n = sub.add_parser("next", help="show the next-ranked cause (no model call)")
    n.add_argument("--json", action="store_true")
    n.set_defaults(func=cmd_next)

    v = sub.add_parser("view", help="open an HTML view with the ranked causes and a diagram")
    v.add_argument("n", nargs="?", type=int, default=1)
    v.set_defaults(func=cmd_view)

    s = sub.add_parser("stats", help="summarize past runs")
    s.set_defaults(func=cmd_stats)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
