"""Orchestrates: parse -> Jev gate -> (Claude candidates -> Jev score) -> validate -> rank -> save.
Returns a plain dict (the same thing saved to .traceroot/last.json)."""
import sys
import time
from datetime import datetime
from pathlib import Path

from . import claude_client, config, jev_client, store, trace_parser
from .trace_parser import ParsedTrace

MAX_TRACEBACK_CHARS = 6000
MAX_SLICE_CHARS = 40000          # Jev's input limit is ~64k tokens; stay well under it

# One-line fixes for the quick (Jev gate) answer, by category.
QUICK_FIX = {
    "missing_import_or_module": "add the missing import, or install the package",
    "undefined_name_or_typo": "fix the spelling, or define the name before it is used",
    "wrong_type": "convert the value to the expected type where it is created",
    "none_value": "find where the value became None; return a real value or guard it",
    "wrong_arguments": "match the call to the function signature",
    "key_or_index_error": "check the key or index; use .get() or a bounds check",
    "file_not_found": "fix the path, or create the file, or resolve it relative to __file__",
    "syntax_error": "fix the syntax at the marked line",
}


def est_tokens(text: str) -> int:
    return len(text) // 4


def notice(msg: str) -> None:
    print(f"traceroot: {msg}", file=sys.stderr)


# ---------- prompt inputs ----------

def traceback_text(parsed: ParsedTrace) -> str:
    raw = parsed.raw.strip()
    return raw if len(raw) <= MAX_TRACEBACK_CHARS else "...(trimmed)...\n" + raw[-MAX_TRACEBACK_CHARS:]


def slices_text(parsed: ParsedTrace) -> str:
    parts = [f"--- {s.file} (lines {s.start}-{s.end}) ---\n{s.text}" for s in parsed.slices]
    text = "\n\n".join(parts) or "(no project source available)"
    return text if len(text) <= MAX_SLICE_CHARS else text[:MAX_SLICE_CHARS] + "\n...(trimmed)"


# ---------- validation ----------

def _prob(v) -> float | None:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 1.0 else None


def validate_candidates(raw: list, root: Path) -> list[dict]:
    """Keep well-formed candidates; null out bad files/lines/probabilities rather than trusting them."""
    out, seen = [], set()
    for i, c in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(c, dict) or not str(c.get("title") or "").strip():
            continue
        cid = str(c.get("id") or f"c{i + 1}")
        if cid in seen:
            cid = f"c{i + 1}"
        seen.add(cid)

        file, line = c.get("file"), c.get("line")
        p = trace_parser.resolve_in_project(file, root) if isinstance(file, str) and file.strip() else None
        file = p.relative_to(root).as_posix() if p else None
        try:
            line = int(line) if file and int(line) > 0 else None
        except (TypeError, ValueError):
            line = None

        category = c.get("category")
        try:
            rank = int(c.get("claude_rank"))
        except (TypeError, ValueError):
            rank = i + 1
        out.append({
            "id": cid,
            "title": " ".join(str(c["title"]).split()[:12]),
            "explanation": str(c.get("explanation") or "").strip(),
            "category": category if category in config.CATEGORIES else "other_or_complex",
            "file": file,
            "line": line,
            "fix_hint": str(c.get("fix_hint") or "").strip(),
            "claude_rank": rank,
            "claude_confidence": _prob(c.get("claude_confidence")),
            "jev_p": None,
        })
    return out[:6]


# ---------- answers ----------

def crash_site(parsed: ParsedTrace) -> tuple[str | None, int | None]:
    if parsed.project_frames:
        fr = parsed.project_frames[-1]
        p = trace_parser.resolve_in_project(fr.file)
        if p:
            return p.relative_to(config.PROJECT_ROOT).as_posix(), fr.line
    return None, None


def quick_answer(parsed: ParsedTrace, gate: dict) -> dict:
    file, line = crash_site(parsed)
    cat = gate["category"]
    return {"id": "q1", "title": parsed.error_line[:80], "explanation": parsed.error_line,
            "category": cat, "file": file, "line": line, "fix_hint": QUICK_FIX.get(cat, ""),
            "claude_rank": None, "claude_confidence": None, "jev_p": gate["probability"]}


def fallback_answer(parsed: ParsedTrace, why: str) -> dict:
    """Used when Claude fails: point at the crash site so the user still gets something useful."""
    file, line = crash_site(parsed)
    return {"id": "f1", "title": f"crash site: {parsed.error_line[:60]}", "explanation": why,
            "category": "other_or_complex", "file": file, "line": line,
            "fix_hint": "inspect the marked line; rerun when the model is available",
            "claude_rank": None, "claude_confidence": None, "jev_p": None}


def rank(causes: list[dict]) -> tuple[list[dict], str]:
    """Final order = Jev probability when every cause has one, else Claude's rank."""
    if causes and all(c["jev_p"] is not None for c in causes):
        causes.sort(key=lambda c: -c["jev_p"])
        order_by = "jev"
    else:
        causes.sort(key=lambda c: (c["claude_rank"] is None, c["claude_rank"] or 0,
                                   -(c["claude_confidence"] or 0)))
        order_by = "claude"
    for i, c in enumerate(causes, 1):
        c["final_rank"] = i
    return causes, order_by


# ---------- main entry ----------

def analyze(text: str, extra_file: str | None = None) -> dict:
    t0 = time.perf_counter()
    root = config.PROJECT_ROOT
    parsed = trace_parser.parse(text, root)
    if extra_file:
        s = trace_parser.slice_for_file(extra_file, root)
        if s:
            parsed.slices.append(s)
        else:
            notice(f"--file {extra_file} is outside the project, blocked, or missing; ignored")
    if not parsed.is_python:
        notice("no Python traceback found; analyzing the raw error text without source context")

    tb, sl = traceback_text(parsed), slices_text(parsed)
    claude_meta, order_by = None, None
    jev_start = jev_client.last_usage["input_tokens"] + jev_client.last_usage["output_tokens"]

    gate = jev_client.gate(tb, sl)
    confident = bool(gate) and gate["category"] != "other_or_complex" \
        and gate["probability"] >= config.GATE_THRESHOLD
    if confident:
        source, causes, order_by = "jev_gate", [quick_answer(parsed, gate)], "jev_gate"
        causes[0]["final_rank"] = 1
    else:
        source = "full"
        try:
            data = claude_client.ask_claude(claude_client.candidates_prompt(parsed.error_line, tb, sl),
                                            claude_client.CANDIDATE_SCHEMA)
            claude_meta = data.pop("_meta", None)
            causes = validate_candidates(data.get("candidates"), root)
            if not causes:
                raise claude_client.ClaudeError("Claude returned no usable candidates")
        except claude_client.ClaudeError as e:
            notice(str(e))
            source, causes = "fallback", [fallback_answer(parsed, str(e))]

        if source == "full":
            scores = jev_client.score(tb, sl, causes)
            if scores and len(scores) == len(causes):
                for c, p in zip(causes, scores):
                    c["jev_p"] = _prob(p)
        causes, order_by = rank(causes)

    referenced = {s.file for s in parsed.slices}
    raw_text = parsed.raw + "".join(_read(root / f) for f in referenced)
    result = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "error_type": parsed.exc_type,
        "error_line": parsed.error_line,
        "source": source,                       # jev_gate | full | fallback
        "order_by": order_by,                   # jev | claude | jev_gate
        "gate": gate,
        "causes": causes,
        "frames": [{"file": f.file, "line": f.line, "func": f.func} for f in parsed.project_frames],
        "meta": {
            "backend": (claude_meta or {}).get("backend"),
            "claude_tokens": (claude_meta or {}).get("tokens", 0),
            "claude_cost_usd": (claude_meta or {}).get("cost_usd", 0.0),
            "jev_tokens": jev_client.last_usage["input_tokens"] + jev_client.last_usage["output_tokens"]
            - jev_start,
            "raw_tokens": est_tokens(raw_text),
            "latency_ms": int((time.perf_counter() - t0) * 1000),
        },
    }
    store.save(result)
    return result


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ---------- output ----------

def format_cause(cause: dict, idx: int, total: int) -> str:
    """Compact, agent-friendly output (few tokens)."""
    if cause.get("jev_p") is not None:
        score = f"p={cause['jev_p']:.2f}"
    elif cause.get("claude_confidence") is not None:
        score = f"claude={cause['claude_confidence']:.2f}"
    else:
        score = "unscored"
    where = f" {cause['file']}:{cause['line']}" if cause.get("file") and cause.get("line") else \
        f" {cause['file']}" if cause.get("file") else ""
    lines = [f"[{idx + 1}/{total}] {cause['category']} ({score}){where}",
             f"cause: {cause['title']}",
             f"fix: {cause['fix_hint'] or '(none given)'}"]
    lines.append("more: `traceroot next`" if idx + 1 < total else "more: none (last candidate)")
    return "\n".join(lines)
