"""End-to-end agent trial: does a real Claude Code agent use TraceRoot via the skill, and what does it cost?

    python bench/agent_trial.py shop-01 [--model claude-haiku-5-5]

Builds the mutated case in a temp folder OUTSIDE this repo, then runs headless Claude Code twice on
the same task: (A) with the TraceRoot skill installed in that project, (B) without it. Reports the
commands the agent ran, whether the mutated line got fixed, and total tokens. Calls models.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(BENCH.parent))

from cases import PROJECTS  # noqa: E402
from mutate import build  # noqa: E402

from traceroot import config  # noqa: E402

TASK = ("The command `python main.py` fails with an error. Find the root cause and fix it with the "
        "smallest change. Then run `python main.py` again to confirm it works.")
TOOLS = ["Bash", "Read", "Edit", "Grep", "Glob"]


def run_agent(workdir: Path, model: str) -> dict:
    exe = config.claude_bin()
    env = dict(os.environ)
    venv_scripts = str(Path(sys.executable).parent)            # so `traceroot` is on the agent's PATH
    env["PATH"] = venv_scripts + os.pathsep + env.get("PATH", "")
    cmd = [exe, "-p", TASK, "--model", model, "--output-format", "stream-json", "--verbose",
           "--strict-mcp-config", "--permission-mode", "acceptEdits", "--allowedTools", *TOOLS]
    proc = subprocess.run(cmd, cwd=workdir, env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=600)
    commands, result = [], {}
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    inp = block.get("input", {})
                    commands.append(f"{block['name']}: {inp.get('command') or inp.get('file_path') or inp.get('pattern') or ''}"[:140])
        if ev.get("type") == "result":
            result = ev
    u = result.get("usage") or {}
    return {"commands": commands, "turns": result.get("num_turns"), "is_error": result.get("is_error"),
            "input_tokens": sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens",
                                                              "cache_creation_input_tokens")),
            "output_tokens": int(u.get("output_tokens") or 0), "cost_usd": result.get("total_cost_usd"),
            "final": (result.get("result") or "")[-400:]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--only", choices=["A", "B"], help="run just one arm")
    ap.add_argument("--tag", default="", help="suffix for the saved JSON")
    a = ap.parse_args()
    project = next(p for p, s in PROJECTS.items() if any(m["id"] == a.case for m in s["mutations"]))
    spec = PROJECTS[project]
    mut = next(m for m in spec["mutations"] if m["id"] == a.case)
    case = build(project, spec, mut)
    out = {}
    for label, with_skill in (("A_with_traceroot", True), ("B_without", False)):
        if a.only and not label.startswith(a.only):
            continue
        work = Path(tempfile.mkdtemp(prefix=f"trt-agent-{a.case}-"))
        shutil.copytree(case.root, work, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".traceroot"))
        if with_skill:
            subprocess.run([str(Path(sys.executable).parent / "traceroot"), "install-skill", "--project"],
                           cwd=work, capture_output=True)
        r = run_agent(work, a.model)
        fixed_line = (work / case.truth_file).read_text(encoding="utf-8").splitlines()[case.truth_line - 1]
        clean = (BENCH / "projects" / project / case.truth_file).read_text(encoding="utf-8").splitlines()[case.truth_line - 1]
        check = subprocess.run(f'"{sys.executable}" main.py', shell=True, cwd=work, capture_output=True)
        r |= {"used_traceroot": any("traceroot" in c or "trt " in c for c in r["commands"]),
              "bug_line_fixed": fixed_line.strip() == clean.strip() or fixed_line != (case.root / case.truth_file)
              .read_text(encoding="utf-8").splitlines()[case.truth_line - 1],
              "program_runs_now": check.returncode == 0, "workdir": str(work)}
        out[label] = r
        print(f"\n=== {label}: turns={r['turns']} tokens in={r['input_tokens']:,} out={r['output_tokens']:,} "
              f"cost=${r['cost_usd']} used_traceroot={r['used_traceroot']} runs_now={r['program_runs_now']} "
              f"bug_line_changed={r['bug_line_fixed']}")
        for c in r["commands"]:
            print("   ", c)
    (BENCH / "out").mkdir(exist_ok=True)
    (BENCH / "out" / f"agent_trial_{a.case}{a.tag}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
