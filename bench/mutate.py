"""Build one benchmark case: copy a clean project, apply one mutation, run it, confirm it crashes."""
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BENCH = Path(__file__).resolve().parent
PROJECTS_DIR = BENCH / "projects"
WORK_DIR = BENCH / "out" / "work"


@dataclass
class Case:
    id: str
    project: str
    kind: str
    distance: str
    root: Path            # the mutated copy
    cmd: str
    truth_file: str       # posix path relative to root
    truth_line: int
    crash_ok: bool
    stderr: str = ""
    crash_file: str | None = None
    crash_line: int | None = None


def python_cmd(cmd: str) -> str:
    """Use this interpreter for `python ...` so cases run the same everywhere."""
    return f'"{sys.executable}"{cmd[len("python"):]}' if cmd.startswith("python ") else cmd


def build(project: str, spec: dict, mut: dict) -> Case:
    src = PROJECTS_DIR / project
    dst = WORK_DIR / mut["id"]
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", ".traceroot"))

    target = dst / mut["file"]
    text = target.read_text(encoding="utf-8")
    count = text.count(mut["find"])
    if count != 1:
        raise ValueError(f"{mut['id']}: snippet occurs {count} times in {mut['file']}, need exactly 1")
    line = text[:text.index(mut["find"])].count("\n") + 1
    target.write_text(text.replace(mut["find"], mut["replace"]), encoding="utf-8")

    case = Case(id=mut["id"], project=project, kind=mut["kind"], distance=mut["distance"], root=dst,
                cmd=python_cmd(spec["cmd"]), truth_file=mut["file"], truth_line=line,
                crash_ok=mut.get("crash_ok", False))
    proc = subprocess.run(case.cmd, shell=True, cwd=dst, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60)
    if proc.returncode == 0 or "Traceback" not in proc.stderr:
        raise RuntimeError(f"{mut['id']}: mutation did not crash (exit {proc.returncode})")
    case.stderr = proc.stderr
    return case
