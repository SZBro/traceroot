"""TraceRoot CLI: traceroot / trt  (analyze | next | view | stats)."""
import argparse
import json
import os
import sys
from pathlib import Path

from . import pipeline, stats, store, trace_parser

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
    if args.json:
        shown = _show(result["causes"][0], 0, len(result["causes"]), True)
    else:
        shown = pipeline.format_top(result)
        print(shown)
    try:
        stats.append(result, shown)
    except OSError as e:
        print(f"traceroot: could not write runs.csv ({e})", file=sys.stderr)
    return 0


def cmd_next(args) -> int:
    if store.load() is None:
        print("traceroot: nothing saved yet; run `traceroot analyze` first")
        return 1
    step = store.advance()
    if step is None:
        print(NO_MORE)
        return 0
    cause, idx, total = step
    if args.json:
        _show(cause, idx, total, True)
    else:
        claude_ordered = (store.load() or {}).get("order_by") == "claude"
        print(pipeline.format_cause(cause, idx, total, both_scores=claude_ordered))
    return 0


def _show(cause: dict, idx: int, total: int, as_json: bool) -> str:
    """Print one cause and return exactly what was printed (used for returned_tokens)."""
    if as_json:
        text = json.dumps({"index": idx + 1, "total": total, **cause}, indent=2)
    else:
        text = pipeline.format_cause(cause, idx, total)
    print(text)
    return text


def cmd_view(args) -> int:
    from . import render_html
    return 0 if render_html.render(args.n, open_browser=not args.no_open) else 1


def cmd_stats(args) -> int:
    print(stats.format_summary(stats.summarize(stats.load_rows())))
    if stats.csv_path().exists():
        print(f"\nper-run rows: {stats.csv_path()}")
    return 0


SKILL_SOURCE = Path(__file__).resolve().parent / "data" / "SKILL.md"


def cmd_install_skill(args) -> int:
    """Copy the Claude Code skill to ~/.claude/skills (all projects) or ./.claude/skills (this project)."""
    base = Path.cwd() if args.project else Path.home()
    dest = base / ".claude" / "skills" / "traceroot" / "SKILL.md"
    if dest.exists() and not args.force and dest.read_text(encoding="utf-8") != SKILL_SOURCE.read_text(encoding="utf-8"):
        print(f"traceroot: {dest} already exists and differs; rerun with --force to overwrite")
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(SKILL_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"traceroot: installed the Claude Code skill at {dest}")
    print("  restart Claude Code (or start a new session) so it picks the skill up")
    return 0


def cmd_check(args) -> int:
    """Check the setup without spending anything: claude binary, Jev key present, parser works."""
    from . import config
    ok = True
    exe = config.claude_bin()
    print(f"[{'ok' if exe else 'FAIL'}] claude CLI: {exe or 'not found (install Claude Code or set TRACEROOT_CLAUDE_BIN)'}")
    ok &= bool(exe)
    key = bool(os.environ.get("TYPESAFE_API_KEY", "").strip())
    print(f"[{'ok' if key else 'warn'}] TYPESAFE_API_KEY: {'set' if key else 'missing (Jev disabled; Claude-only ranking)'}"
          f"  (looked in env, ./.env, {config.USER_CONFIG})")
    parsed = trace_parser.parse_traceback('Traceback (most recent call last):\n  File "x.py", line 1, in <module>\n'
                                          "NameError: name 'y' is not defined\n")
    good = parsed.exc_type == "NameError" and len(parsed.frames) == 1
    print(f"[{'ok' if good else 'FAIL'}] traceback parser")
    ok &= good
    print(f"[info] project root: {config.PROJECT_ROOT}  (state in {config.STATE_DIR})")
    for scope, path in (("user", Path.home()), ("project", Path.cwd())):
        skill = path / ".claude" / "skills" / "traceroot" / "SKILL.md"
        print(f"[{'ok' if skill.exists() else 'info'}] {scope} skill: {skill if skill.exists() else 'not installed'}")
    if args.live:
        from . import claude_client
        try:
            claude_client.ask_claude('Reply with only this JSON: {"ok": true}')
            print("[ok] live Claude call")
        except claude_client.ClaudeError as e:
            print(f"[FAIL] live Claude call: {e}")
            ok = False
    return 0 if ok else 1


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
    v.add_argument("n", nargs="?", type=int, default=1, help="which cause to diagram (default 1)")
    v.add_argument("--no-open", action="store_true", help="write the file but don't open a browser")
    v.set_defaults(func=cmd_view)

    s = sub.add_parser("stats", help="summarize past runs")
    s.set_defaults(func=cmd_stats)

    i = sub.add_parser("install-skill", help="install the Claude Code skill (default: for all your projects)")
    i.add_argument("--project", action="store_true", help="install into ./.claude/skills instead of ~/.claude/skills")
    i.add_argument("--force", action="store_true", help="overwrite an existing, different skill file")
    i.set_defaults(func=cmd_install_skill)

    c = sub.add_parser("check", help="verify the setup (claude CLI, Jev key, parser, skill)")
    c.add_argument("--live", action="store_true", help="also make one tiny Claude call")
    c.set_defaults(func=cmd_check)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
