"""Parse Python tracebacks into frames and read safe code slices around them. Plain code, no AI."""
import ast
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
    label: str = ""              # e.g. "definition of load_catalog, used in main()"


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
    parsed.slices += related_definitions(kept, parsed.slices, root)
    return parsed


# ---------- one-hop definitions ----------
# The root cause is often in code that already returned (so it is not on the stack): a function imported
# from another project file, or a module-level constant far from the crash. For each traceback function,
# find the project names it uses and add just their definitions.

def _module_file(module: str | None, level: int, here: Path, root: Path) -> Path | None:
    """Resolve an import (`from <level dots><module> import ...`) to a project .py file, or None."""
    if level:
        base = here.parent
        for _ in range(level - 1):
            base = base.parent
    else:
        base = root
    parts = module.split(".") if module else []
    target = base.joinpath(*parts) if parts else base
    for cand in (target.with_suffix(".py"), target / "__init__.py"):
        p = resolve_in_project(str(cand), root)
        if p:
            return p
    return None


def _top_level_defs(tree: ast.Module) -> dict[str, ast.stmt]:
    defs = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    defs[t.id] = node
    return defs


def _imports(tree: ast.Module, here: Path, root: Path) -> tuple[dict, dict]:
    """-> (names: local name -> (file, original name), modules: local alias -> file), project-only."""
    names, modules = {}, {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            src = _module_file(node.module, node.level, here, root)
            for a in node.names:
                local = a.asname or a.name
                sub = _module_file(f"{node.module}.{a.name}" if node.module else a.name, node.level, here, root)
                if sub:                                   # `from . import pricing` -> a module
                    modules[local] = sub
                elif src:
                    names[local] = (src, a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                src = _module_file(a.name, 0, here, root)
                if src:
                    modules[a.asname or a.name.split(".")[0]] = src
    return names, modules


_TREES: dict[Path, tuple[ast.Module, list[str]] | None] = {}


def _parse_file(p: Path):
    if p not in _TREES:
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
            _TREES[p] = (ast.parse(src), src.splitlines())
        except (OSError, SyntaxError, ValueError):
            _TREES[p] = None
    return _TREES[p]


def _enclosing_function(tree: ast.Module, line: int):
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                node.lineno <= line <= (node.end_lineno or node.lineno):
            if best is None or node.lineno >= best.lineno:
                best = node
    return best


def _assigned_names(stmt: ast.stmt) -> set[str]:
    targets = []
    if isinstance(stmt, ast.Assign):
        targets = stmt.targets
    elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
        targets = [stmt.target]
    elif isinstance(stmt, (ast.For, ast.AsyncFor)):
        targets = [stmt.target]
    elif isinstance(stmt, (ast.With, ast.AsyncWith)):
        targets = [i.optional_vars for i in stmt.items if i.optional_vars]
    return {n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)}


def _value_part(stmt: ast.stmt) -> list[ast.AST]:
    """The right-hand side of an assignment-like statement (what the assigned names come from)."""
    if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        return [stmt.value] if stmt.value else []
    if isinstance(stmt, (ast.For, ast.AsyncFor)):
        return [stmt.iter]
    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        return [i.context_expr for i in stmt.items]
    return []


def _frame_nodes(func, line: int, is_crash: bool) -> list[ast.AST]:
    """Code whose names we follow. Short crash function: all of it. Otherwise: the statement (or call) on
    the frame line plus the earlier local assignments that feed it (two rounds of def-use)."""
    if is_crash and (func.end_lineno or func.lineno) - func.lineno <= config.WHOLE_FUNC_LINES:
        return [func]
    stmts = [n for n in ast.walk(func) if isinstance(n, ast.stmt) and n is not func
             and n.lineno <= line <= (n.end_lineno or n.lineno)]
    if not stmts:
        return [func]
    here = min(stmts, key=lambda n: (n.end_lineno or n.lineno) - n.lineno)
    if (here.end_lineno or here.lineno) > here.lineno:   # multi-line statement: narrow to the call on the line
        calls = [n for n in ast.walk(here) if isinstance(n, ast.Call)
                 and n.lineno <= line <= (n.end_lineno or n.lineno)]
        if calls:
            here = min(calls, key=lambda n: ((n.end_lineno or n.lineno) - n.lineno, -n.lineno))
    nodes = [here]
    needed = {n.id for n in ast.walk(here) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    earlier = [n for n in ast.walk(func) if isinstance(n, ast.stmt) and n.lineno < here.lineno]
    for _ in range(2):
        found = set()
        for st in earlier:
            if _assigned_names(st) & needed:
                parts = _value_part(st)
                nodes += parts
                found |= {n.id for p in parts for n in ast.walk(p)
                          if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        needed = found - needed
        if not needed:
            break
    return nodes


def related_definitions(kept: list, slices: list[CodeSlice], root: Path,
                        max_def_lines: int = config.MAX_DEF_LINES,
                        max_total: int = config.MAX_RELATED_LINES) -> list[CodeSlice]:
    """Definitions (one hop) of project names used by the traceback functions, crash site first."""
    covered = [(s.file, s.start, s.end) for s in slices]
    out, seen, total = [], set(), 0
    crash_frame = kept[-1][0] if kept else None
    for fr, p in reversed(kept):                     # crash frame first: its names matter most
        parsed = _parse_file(p)
        if not parsed:
            continue
        tree, _ = parsed
        func = _enclosing_function(tree, fr.line)
        if func is None:
            continue
        local_defs = _top_level_defs(tree)
        imp_names, imp_modules = _imports(tree, p, root)
        wanted = []                                  # (file, name) in order of first use
        scope = _frame_nodes(func, fr.line, fr is crash_frame)
        for node in (n for part in scope for n in ast.walk(part)):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in local_defs and node.id != func.name:
                    wanted.append((p, node.id))
                elif node.id in imp_names:
                    wanted.append(imp_names[node.id])
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                    and node.value.id in imp_modules:
                wanted.append((imp_modules[node.value.id], node.attr))
        for file, name in sorted(set(wanted), key=wanted.index):
            if (file, name) in seen:
                continue
            seen.add((file, name))
            target = _parse_file(file)
            node = target and _top_level_defs(target[0]).get(name)
            if not node:
                continue
            start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
            end = node.end_lineno or node.lineno
            if isinstance(node, ast.ClassDef):           # header + fields only, not every method
                methods = [b.lineno for b in node.body if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))]
                if methods:
                    end = max(node.lineno, min(methods) - 1)
            rel = file.relative_to(root).as_posix()
            if any(f == rel and s <= start and end <= e for f, s, e in covered):
                continue                             # already inside a frame window
            end = min(end, start + max_def_lines - 1)
            if total + (end - start + 1) > max_total:
                continue
            total += end - start + 1
            covered.append((rel, start, end))
            lines = target[1]
            width = len(str(end))
            text = "\n".join(f"   {n:>{width}} | {lines[n - 1]}" for n in range(start, end + 1))
            truncated = end < (node.end_lineno or end) and not isinstance(node, ast.ClassDef)
            out.append(CodeSlice(file=rel, start=start, end=end, error_line=0,
                                 text=text + ("\n   ... (truncated)" if truncated else ""),
                                 label=f"definition of {name}, used in {func.name}()"))
    return out


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
