"""Parse Python tracebacks into frames and read safe code slices around them. Plain code, no AI."""
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import config

FRAME_RE = re.compile(r'^\s*File "(?P<file>.+?)", line (?P<line>\d+)(?:, in (?P<func>.+))?\s*$')
EXC_RE = re.compile(r"^(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning|Iteration))"
                    r"(?::\s?(?P<msg>.*))?$")
GENERIC_EXC_RE = re.compile(r"^(?P<type>[A-Za-z_][\w.]*)(?::\s?(?P<msg>.*))?$")
TRACEBACK_HEADER ="Traceback (most recent call last):"


@dataclass
class Frame:
    file: str
    line: int
    func: str | None = None
    code: str | None = None      # the source line Python printed under the frame, if any


@dataclass
class CodeSlice:
    file: str                    # path relative to the project root
    start: int
    end: int
    error_line: int              # the frame line closest to the crash in this slice
    text: str                    # numbered lines, every frame line marked with ">>"
    marks: list[int] = field(default_factory=list)


@dataclass
class ParsedTrace:
    raw: str
    exc_type: str | None = None
    message: str | None = None
    frames: list[Frame] = field(default_factory=list)          # every frame in the last traceback
    project_frames: list[Frame] = field(default_factory=list)  # last MAX_FRAMES inside the project
    slices: list[CodeSlice] = field(default_factory=list)

    @property
    def is_python(self) -> bool:
        return bool(self.frames) or self.exc_type is not None

    @property
    def error_line(self) -> str:
        if not self.exc_type:
            return self.raw.strip().splitlines()[-1] if self.raw.strip() else ""
        return f"{self.exc_type}: {self.message}" if self.message else self.exc_type


# ---------- parsing ----------

def parse_traceback(text: str) -> ParsedTrace:
    """Parse the last traceback in `text` (for chained exceptions, the last one is what crashed)."""
    result = ParsedTrace(raw=text)
    lines = text.replace("\r\n", "\n").split("\n")

    start = 0
    for i, ln in enumerate(lines):
        if ln.strip() == TRACEBACK_HEADER:
            start = i
    block = lines[start:]

    for i, ln in enumerate(block):
        m = FRAME_RE.match(ln)
        if m:
            code = None
            nxt = block[i + 1] if i + 1 < len(block) else ""
            if nxt.startswith("    ") and not FRAME_RE.match(nxt) and not _is_caret_line(nxt):
                code = nxt.strip()
            result.frames.append(Frame(file=m["file"], line=int(m["line"]),
                                       func=(m["func"] or "").strip() or None, code=code))

    # The exception line is the last unindented line that looks like `SomeError: message`.
    # Fallback for custom names (e.g. `CartEmpty: ...`): the last unindented line after the frames.
    unindented = [ln.strip() for ln in block if ln.strip() and not ln.startswith(" ")
                  and ln.strip() != TRACEBACK_HEADER]
    m = next((EXC_RE.match(ln) for ln in reversed(unindented) if EXC_RE.match(ln)), None)
    if m is None and result.frames and unindented:
        m = GENERIC_EXC_RE.match(unindented[-1])
    if m:
        result.exc_type, result.message = m["type"], (m["msg"] or "").strip() or None
    return result


def _is_caret_line(line: str) -> bool:
    s = line.strip()
    return bool(s) and set(s) <= set("^~ ")


# ---------- safety ----------

def resolve_in_project(path: str, root: Path | None = None) -> Path | None:
    """Return the resolved path if it is a readable, safe file inside the project root, else None."""
    root = (root or config.PROJECT_ROOT).resolve()
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    try:
        p = p.resolve()
        rel = p.relative_to(root)
    except (OSError, ValueError):
        return None                      # outside the project root
    if _is_blocked(rel) or _is_stdlib(p) or not p.is_file():
        return None
    return p


def _is_blocked(rel: Path) -> bool:
    name = rel.name.lower()
    if name in config.BLOCKED_NAMES or name.startswith(".env"):
        return True
    if rel.suffix.lower() in config.BLOCKED_SUFFIXES:
        return True
    return any(part.lower() in config.BLOCKED_DIRS for part in rel.parts[:-1])


def _is_stdlib(p: Path) -> bool:
    for base in {sys.base_prefix, sys.prefix}:
        try:
            p.relative_to(Path(base).resolve())
            return True
        except ValueError:
            pass
    return False


# ---------- code slices ----------

def read_slices(path: Path, lines: list[int], radius: int = config.CONTEXT_LINES,
                root: Path | None = None) -> list[CodeSlice]:
    """Read ±radius lines around each line in `lines`, merging windows that overlap or touch,
    so frames in the same file never send the same code twice. `lines` is crash-site last."""
    root = (root or config.PROJECT_ROOT).resolve()
    try:
        src = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    if not src:
        return []
    lines = [min(max(n, 1), len(src)) for n in lines]
    windows = sorted((max(1, n - radius), min(len(src), n + radius)) for n in lines)
    merged: list[list[int]] = []
    for start, end in windows:
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    rel = path.relative_to(root).as_posix()
    out = []
    for start, end in merged:
        marks = [n for n in lines if start <= n <= end]
        width = len(str(end))
        text = "\n".join(f"{'>>' if n in marks else '  '} {n:>{width}} | {src[n - 1]}"
                         for n in range(start, end + 1))
        out.append(CodeSlice(file=rel, start=start, end=end, error_line=marks[-1],
                             text=text, marks=sorted(set(marks))))
    return out


def attach_context(parsed: ParsedTrace, root: Path | None = None,
                   max_frames: int = config.MAX_FRAMES) -> ParsedTrace:
    """Keep the last `max_frames` frames inside the project and read merged slices around them."""
    root = (root or config.PROJECT_ROOT).resolve()
    kept = []
    for fr in reversed(parsed.frames):
        p = resolve_in_project(fr.file, root)
        if p is None:
            continue
        kept.append((fr, p))
        if len(kept) == max_frames:
            break
    kept.reverse()                                   # outermost first, crash site last
    parsed.project_frames = [fr for fr, _ in kept]

    by_file: dict[Path, list[int]] = {}              # insertion order = order files first appear
    for fr, p in kept:
        by_file.setdefault(p, []).append(fr.line)
    parsed.slices = [s for p, lines in by_file.items() for s in read_slices(p, lines, root=root)]
    return parsed


def slice_for_file(path: str, root: Path | None = None) -> CodeSlice | None:
    """For `--file` with no traceback: the top of the file, up to 2 * CONTEXT_LINES + 1 lines."""
    p = resolve_in_project(path, root)
    if p is None:
        return None
    slices = read_slices(p, [1 + config.CONTEXT_LINES], root=root)
    return slices[0] if slices else None


# ---------- input ----------

def run_command(cmd: str, root: Path | None = None,
                timeout: int = config.RUN_TIMEOUT_S) -> tuple[int, str]:
    """Run `cmd` in the project root and return (exit code, stderr). Used by `analyze --run`."""
    root = (root or config.PROJECT_ROOT).resolve()
    try:
        proc = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return -1, f"TimeoutError: command did not finish within {timeout}s: {cmd}"
    return proc.returncode, proc.stderr or proc.stdout


def parse(text: str, root: Path | None = None) -> ParsedTrace:
    """Parse traceback text and attach safe code slices."""
    return attach_context(parse_traceback(text), root)
