"""Append one row per `analyze` to .traceroot/runs.csv, and summarize them for `traceroot stats`.
Token counts for text are estimates: len(text) // 4. Model token counts come from the APIs."""
import csv
from pathlib import Path

from . import config

FIELDS = ["timestamp", "error_type", "path", "gate_category", "gate_p", "claude_top", "jev_top", "agree",
          "raw_tokens", "returned_tokens", "claude_tokens", "jev_tokens", "latency_ms", "backend"]


def csv_path() -> Path:
    return config.STATE_DIR / "runs.csv"


def _loc(c: dict | None) -> str:
    if not c:
        return ""
    return f"{c['file']}:{c['line']}" if c.get("file") and c.get("line") else c.get("id", "")


def tops(result: dict) -> tuple[dict | None, dict | None]:
    """Claude's #1 (lowest claude_rank) and Jev's #1 (highest jev_p) among the saved causes."""
    causes = result.get("causes") or []
    ranked = [c for c in causes if c.get("claude_rank")]
    scored = [c for c in causes if c.get("jev_p") is not None]
    return (min(ranked, key=lambda c: c["claude_rank"]) if ranked else None,
            max(scored, key=lambda c: c["jev_p"]) if scored else None)


def row_for(result: dict, returned_tokens: int) -> dict:
    gate, meta = result.get("gate") or {}, result.get("meta") or {}
    claude_top, jev_top = tops(result)
    path = "jev_gate" if result["source"] == "jev_gate" else result["source"]   # full | fallback
    if result["source"] == "full" and claude_top and jev_top:
        agree = "yes" if claude_top["id"] == jev_top["id"] else "no"
    else:
        agree = ""
    return {
        "timestamp": result.get("timestamp", ""),
        "error_type": result.get("error_type") or "",
        "path": path,
        "gate_category": gate.get("category", ""),
        "gate_p": gate.get("probability", ""),
        "claude_top": _loc(claude_top),
        "jev_top": _loc(jev_top),
        "agree": agree,
        "raw_tokens": meta.get("raw_tokens", 0),
        "returned_tokens": returned_tokens,
        "claude_tokens": meta.get("claude_tokens", 0),
        "jev_tokens": meta.get("jev_tokens", 0),
        "latency_ms": meta.get("latency_ms", 0),
        "backend": meta.get("backend") or "",
    }


def append(result: dict, returned_text: str) -> None:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    p = csv_path()
    new = not p.exists() or p.stat().st_size == 0
    with p.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row_for(result, len(returned_text) // 4))


def load_rows() -> list[dict]:
    try:
        with csv_path().open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    gate = sum(r["path"] == "jev_gate" for r in rows)
    compared = [r for r in rows if r["agree"] in ("yes", "no")]
    agreed = sum(r["agree"] == "yes" for r in compared)
    raw = sum(_int(r["raw_tokens"]) for r in rows)
    ret = sum(_int(r["returned_tokens"]) for r in rows)
    reductions = [1 - _int(r["returned_tokens"]) / _int(r["raw_tokens"]) for r in rows if _int(r["raw_tokens"])]
    by_path = {}
    for r in rows:
        d = by_path.setdefault(r["path"], {"runs": 0, "claude": 0, "jev": 0, "ms": 0})
        d["runs"] += 1
        d["claude"] += _int(r["claude_tokens"])
        d["jev"] += _int(r["jev_tokens"])
        d["ms"] += _int(r["latency_ms"])
    return {
        "runs": n,
        "gate_runs": gate,
        "gate_pct": 100 * gate / n if n else 0.0,
        "compared": len(compared),
        "agreed": agreed,
        "agree_pct": 100 * agreed / len(compared) if compared else None,
        "avg_raw": raw / n if n else 0,
        "avg_returned": ret / n if n else 0,
        "avg_reduction_pct": 100 * sum(reductions) / len(reductions) if reductions else None,
        "claude_tokens": sum(d["claude"] for d in by_path.values()),
        "jev_tokens": sum(d["jev"] for d in by_path.values()),
        "by_path": by_path,
    }


def format_summary(s: dict) -> str:
    if not s["runs"]:
        return "traceroot: no runs logged yet; run `traceroot analyze` first"
    agree = f"{s['agreed']}/{s['compared']} ({s['agree_pct']:.0f}%)" if s["compared"] else "n/a (no full runs with Jev)"
    red = f"{s['avg_reduction_pct']:.0f}%" if s["avg_reduction_pct"] is not None else "n/a"
    lines = [
        f"runs:                     {s['runs']}",
        f"handled by Jev gate alone: {s['gate_runs']}/{s['runs']} ({s['gate_pct']:.0f}%)",
        f"Claude/Jev agree on #1:    {agree}",
        f"agent tokens per run:      {s['avg_raw']:.0f} raw -> {s['avg_returned']:.0f} returned "
        f"(avg reduction {red}; estimates, len//4)",
        f"model tokens spent:        {s['claude_tokens'] + s['jev_tokens']} total "
        f"(Claude {s['claude_tokens']}, Jev {s['jev_tokens']})",
        "",
        f"{'path':10} {'runs':>5} {'avg Claude tok':>15} {'avg Jev tok':>12} {'avg ms':>8}",
    ]
    for path, d in sorted(s["by_path"].items()):
        r = d["runs"]
        lines.append(f"{path:10} {r:>5} {d['claude'] / r:>15.0f} {d['jev'] / r:>12.0f} {d['ms'] / r:>8.0f}")
    return "\n".join(lines)
