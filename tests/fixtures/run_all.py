"""Run every planted-bug fixture.

    python tests/fixtures/run_all.py            # traceroot analyze --run on each (calls models)
    python tests/fixtures/run_all.py --capture  # only save each traceback to tracebacks/ (no models)

Run from the TraceRoot folder.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

# fixture -> (expected category, planted bug). The scripts themselves carry no hints, so the
# models can't read the answer off a comment.
FIXTURES = {
    "easy_missing_import.py": ("missing_import_or_module", "uses math.sqrt without `import math`"),
    "easy_typo_name.py": ("undefined_name_or_typo", "returns `totl` instead of `total`"),
    "easy_file_not_found.py": ("file_not_found", "opens settings/config.json, which doesn't exist"),
    "easy_wrong_args.py": ("wrong_arguments", "make_user() called without the `age` argument"),
    "medium_none_cart.py": ("none_value",
                            "load_cart sets items=None for an empty cart (line 5); crash is 3 calls later"),
    "medium_keyerror.py": ("key_or_index_error",
                           "build_profile writes 'user_name' but greeting reads 'username'"),
    "hard_off_by_one.py": ("key_or_index_error",
                           "page_bounds uses total + 1 as the end (line 4); IndexError in page_labels"),
    "hard_str_int.py": ("wrong_type",
                        "parse_order leaves qty as str (line 10); line_total multiplies float * str"),
}


def script_cmd(name: str) -> str:
    return f'"{sys.executable}" tests/fixtures/{name}'


def capture() -> None:
    out_dir = HERE / "tracebacks"
    out_dir.mkdir(exist_ok=True)
    for name in FIXTURES:
        proc = subprocess.run(script_cmd(name), shell=True, cwd=ROOT, capture_output=True, text=True)
        # store project-relative paths so the saved tracebacks work on any machine
        text = proc.stderr.replace(str(ROOT) + "\\", "").replace(str(ROOT) + "/", "")
        text = re.sub(r'File "([^"]+)"', lambda m: 'File "%s"' % m[1].replace("\\", "/"), text)
        (out_dir / f"{Path(name).stem}.txt").write_text(text, encoding="utf-8")
        last = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "(no error)"
        print(f"{name:26} {last}")


def analyze() -> None:
    rows = []
    for name, (expected, bug) in FIXTURES.items():
        print(f"\n=== {name}  (expect: {expected}; planted: {bug})", flush=True)
        subprocess.run(f'traceroot analyze --run "python tests/fixtures/{name}"', shell=True, cwd=ROOT)
        rows.append((Path(name).stem, summarize()))
    print(f"\n{'fixture':22} {'path':8} {'top cause (final)':40} {'claude #1':>10} {'jev #1':>10} agree")
    for stem, s in rows:
        print(f"{stem:22} {s['source']:8} {s['top']:40.40} {s['claude']:>10} {s['jev']:>10} {s['agree']}")


def summarize() -> dict:
    """Read .traceroot/last.json: path taken, top cause, and Claude's vs Jev's #1 pick (as file:line)."""
    d = json.loads((ROOT / ".traceroot" / "last.json").read_text(encoding="utf-8"))
    causes = d["causes"]
    loc = lambda c: f"L{c['line']}" if c and c.get("line") else "-"  # noqa: E731
    top = causes[0]
    claude_top = min((c for c in causes if c.get("claude_rank")), key=lambda c: c["claude_rank"], default=None)
    jev_top = max((c for c in causes if c.get("jev_p") is not None), key=lambda c: c["jev_p"], default=None)
    agree = "-" if not (claude_top and jev_top) else "yes" if claude_top["id"] == jev_top["id"] else "NO"
    return {"source": d["source"], "top": f"{loc(top)} {top['title']}", "claude": loc(claude_top),
            "jev": f"{loc(jev_top)}" + (f" {jev_top['jev_p']:.2f}" if jev_top else ""), "agree": agree}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", action="store_true", help="only save tracebacks, no model calls")
    capture() if ap.parse_args().capture else analyze()
