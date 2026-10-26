"""Benchmark TraceRoot against a "just ask Claude with the full files" baseline.

    python bench/run_bench.py --dry                  # build every case, check it crashes (no models)
    python bench/run_bench.py --project shop         # run one project (calls Jev + Claude)
    python bench/run_bench.py                        # run everything not already in results.jsonl
    python bench/run_bench.py --summarize            # rebuild bench/RESULTS.md from results.jsonl

For each case:
  traceroot  real CLI: `traceroot analyze --run <cmd>` in the mutated copy (gate, Claude, Jev, slices)
  baseline   one Claude call, same model and prompt, but given the traceback + EVERY project source file
             in full (no slicing, no gate, no Jev), ranked by Claude
A cause is a hit if it names the mutated file and a line within +/-1 of the mutated line
(or of the crash line, for cases marked crash_ok).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH.parent))
sys.path.insert(0, str(BENCH))

from cases import PROJECTS  # noqa: E402
from mutate import Case, build  # noqa: E402

from traceroot import claude_client, pipeline, trace_parser  # noqa: E402

OUT = BENCH / "out"
RESULTS = OUT / "results.jsonl"
SUMMARY = BENCH / "RESULTS.md"
TRACEROOT_EXE = Path(sys.executable).parent / ("traceroot.exe" if os.name == "nt" else "traceroot")
LINE_TOLERANCE = 1


def est(text: str) -> int:
    return len(text) // 4


# ---------- scoring ----------

def is_hit(cause: dict, case: Case) -> bool:
    if cause.get("file") != case.truth_file or not cause.get("line"):
        if not (case.crash_ok and cause.get("file") == case.crash_file and cause.get("line")):
            return False
    targets = [(case.truth_file, case.truth_line)]
    if case.crash_ok and case.crash_file:
        targets.append((case.crash_file, case.crash_line))
    return any(cause["file"] == f and abs(int(cause["line"]) - ln) <= LINE_TOLERANCE for f, ln in targets)


def first_hit_rank(causes: list[dict], case: Case) -> int | None:
    return next((i + 1 for i, c in enumerate(causes) if is_hit(c, case)), None)


# ---------- inputs ----------

def project_sources(case: Case) -> list[Path]:
    return sorted(p for p in case.root.rglob("*.py") if ".traceroot" not in p.parts)


def full_source_text(case: Case, parsed) -> str:
    """Every project .py file in full, numbered like TraceRoot's slices, traceback lines marked >>."""
    marks = {}
    for f in parsed.project_frames:
        p = trace_parser.resolve_in_project(f.file, case.root)
        if p:
            marks.setdefault(p.relative_to(case.root).as_posix(), set()).add(f.line)
    parts = []
    for p in project_sources(case):
        rel = p.relative_to(case.root).as_posix()
        lines = p.read_text(encoding="utf-8").splitlines()
        w = len(str(len(lines)))
        body = "\n".join(f"{'>>' if n in marks.get(rel, ()) else '  '} {n:>{w}} | {t}"
                         for n, t in enumerate(lines, 1))
        parts.append(f"--- {rel} (full file, {len(lines)} lines) ---\n{body}")
    return "\n\n".join(parts)


# ---------- methods ----------

def run_traceroot(case: Case) -> dict:
    env = dict(os.environ, TRACEROOT_ROOT=str(case.root))
    t = time.perf_counter()
    proc = subprocess.run([str(TRACEROOT_EXE), "analyze", "--run", case.cmd], cwd=case.root, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    ms = int((time.perf_counter() - t) * 1000)
    last = json.loads((case.root / ".traceroot" / "last.json").read_text(encoding="utf-8"))
    meta = last["meta"]
    causes = last["causes"]
    return {
        "source": last["source"], "gate": last.get("gate"), "causes": causes,
        "top1": first_hit_rank(causes, case) == 1, "hit_rank": first_hit_rank(causes, case),
        "model_tokens": meta["claude_tokens"] + meta["jev_tokens"],
        "claude_tokens": meta["claude_tokens"], "jev_tokens": meta["jev_tokens"],
        "returned_tokens": est(proc.stdout), "latency_ms": ms, "stderr": proc.stderr.strip()[-300:],
    }


def run_baseline(case: Case, parsed) -> dict:
    prompt = claude_client.candidates_prompt(parsed.error_line, case.stderr.strip(), full_source_text(case, parsed))
    t = time.perf_counter()
    try:
        data = claude_client.ask_claude(prompt)
        meta = data.pop("_meta", {})
        causes = pipeline.rank(pipeline.validate_candidates(data.get("candidates"), case.root))[0]
        err = None
    except claude_client.ClaudeError as e:
        causes, meta, err = [], {}, str(e)
    return {
        "causes": causes, "top1": first_hit_rank(causes, case) == 1, "hit_rank": first_hit_rank(causes, case),
        "model_tokens": meta.get("tokens", 0), "prompt_tokens_est": est(prompt),
        "latency_ms": int((time.perf_counter() - t) * 1000), "error": err,
    }


def run_case(project: str, spec: dict, mut: dict, baseline: bool) -> dict:
    case = build(project, spec, mut)
    parsed = trace_parser.parse(case.stderr, case.root)
    if parsed.project_frames:
        crash = parsed.project_frames[-1]
        p = trace_parser.resolve_in_project(crash.file, case.root)
        case.crash_file, case.crash_line = (p.relative_to(case.root).as_posix() if p else None), crash.line
    referenced = {s.file for s in parsed.slices}
    agent_referenced = est(case.stderr) + sum(est((case.root / f).read_text(encoding="utf-8")) for f in referenced)
    agent_project = est(case.stderr) + sum(est(p.read_text(encoding="utf-8")) for p in project_sources(case))

    row = {"id": case.id, "project": project, "kind": case.kind, "distance": case.distance,
           "truth": f"{case.truth_file}:{case.truth_line}", "crash": f"{case.crash_file}:{case.crash_line}",
           "error_line": parsed.error_line,
           "agent_tokens_referenced": agent_referenced, "agent_tokens_project": agent_project,
           "traceroot": run_traceroot(case)}
    if baseline:
        row["baseline"] = run_baseline(case, parsed)
    return row


# ---------- summary ----------

def load_results() -> list[dict]:
    if not RESULTS.exists():
        return []
    return [json.loads(ln) for ln in RESULTS.read_text(encoding="utf-8").splitlines() if ln.strip()]


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


def avg(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def method_stats(rows: list[dict], key: str) -> dict:
    rs = [r[key] for r in rows if key in r]
    return {"n": len(rs), "top1": sum(r["top1"] for r in rs),
            "top3": sum(bool(r["hit_rank"]) and r["hit_rank"] <= 3 for r in rs),
            "any": sum(bool(r["hit_rank"]) for r in rs),
            "tokens": avg(r["model_tokens"] for r in rs), "ms": avg(r["latency_ms"] for r in rs)}


def summarize(rows: list[dict]) -> str:
    tr, bl = method_stats(rows, "traceroot"), method_stats(rows, "baseline")
    gate = [r for r in rows if r["traceroot"]["source"] == "jev_gate"]
    full = [r for r in rows if r["traceroot"]["source"] == "full"]
    out = ["# TraceRoot benchmark results", "",
           f"{len(rows)} mutation cases across {len({r['project'] for r in rows})} projects "
           f"({', '.join(sorted({r['project'] for r in rows}))}). Generated by `bench/run_bench.py`; "
           "a hit = right file, line within +/-1 of the mutated line.", "",
           "## Accuracy and model cost", "",
           "| Method | Top-1 | Top-3 | Found at all | Avg model tokens / case | Avg latency |",
           "|---|---|---|---|---|---|"]
    for name, s in (("TraceRoot", tr), ("Baseline: Claude + full files", bl)):
        if s["n"]:
            out.append(f"| {name} | {pct(s['top1'], s['n'])} | {pct(s['top3'], s['n'])} | {pct(s['any'], s['n'])} "
                       f"| {s['tokens']:,.0f} | {s['ms'] / 1000:.1f} s |")
    if tr["n"] and bl["n"] and bl["tokens"]:
        out += ["", f"TraceRoot used **{100 * (1 - tr['tokens'] / bl['tokens']):.0f}% fewer model tokens** "
                    f"per case than the full-file baseline."]

    out += ["", "## Tokens the calling agent reads", "",
            "| | Avg tokens / case |", "|---|---|",
            f"| Traceback + full files in the traceback | {avg(r['agent_tokens_referenced'] for r in rows):,.0f} |",
            f"| Traceback + every project source file | {avg(r['agent_tokens_project'] for r in rows):,.0f} |",
            f"| TraceRoot compact output (top cause) | {avg(r['traceroot']['returned_tokens'] for r in rows):,.0f} |"]
    red_ref = avg(1 - r["traceroot"]["returned_tokens"] / r["agent_tokens_referenced"] for r in rows)
    red_proj = avg(1 - r["traceroot"]["returned_tokens"] / r["agent_tokens_project"] for r in rows)
    out += ["", f"Average reduction: **{100 * red_ref:.0f}%** vs. reading the traceback's files, "
                f"**{100 * red_proj:.0f}%** vs. reading the whole project. (Text tokens are len//4 estimates.)"]

    out += ["", "## Jev gate", "",
            f"- Answered alone (no Claude call): {pct(len(gate), len(rows))}",
            f"- Gate precision (gate answers that were right): {pct(sum(r['traceroot']['top1'] for r in gate), len(gate))}",
            f"- Avg model tokens: gate path {avg(r['traceroot']['model_tokens'] for r in gate):,.0f}, "
            f"full path {avg(r['traceroot']['model_tokens'] for r in full):,.0f}"]

    out += ["", "## By distance between bug and crash", "",
            "| Distance | Cases | TraceRoot top-1 | Baseline top-1 |", "|---|---|---|---|"]
    for d in ("crash_line", "same_file", "cross_file"):
        sub = [r for r in rows if r["distance"] == d]
        if sub:
            b = [r for r in sub if "baseline" in r]
            out.append(f"| {d} | {len(sub)} | {pct(sum(r['traceroot']['top1'] for r in sub), len(sub))} "
                       f"| {pct(sum(r['baseline']['top1'] for r in b), len(b))} |")

    out += ["", "## Every case", "",
            "| Case | Kind | Distance | Bug at | Crash at | TraceRoot path | TraceRoot hit rank | Baseline hit rank "
            "| TraceRoot tokens | Baseline tokens |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        t, b = r["traceroot"], r.get("baseline", {})
        out.append(f"| {r['id']} | {r['kind']} | {r['distance']} | `{r['truth']}` | `{r['crash']}` | {t['source']} "
                   f"| {t['hit_rank'] or 'miss'} | {b.get('hit_rank') or ('miss' if b else '-')} "
                   f"| {t['model_tokens']:,} | {b.get('model_tokens', 0):,} |")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project")
    ap.add_argument("--cases", help="comma-separated case ids")
    ap.add_argument("--dry", action="store_true", help="only build cases and check they crash")
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument("--rerun", action="store_true", help="rerun cases already in results.jsonl")
    ap.add_argument("--summarize", action="store_true")
    a = ap.parse_args()

    if a.summarize:
        SUMMARY.write_text(summarize(load_results()), encoding="utf-8")
        print(SUMMARY.read_text(encoding="utf-8"))
        return

    OUT.mkdir(parents=True, exist_ok=True)
    done = {r["id"] for r in load_results()} if not a.rerun else set()
    wanted = set(a.cases.split(",")) if a.cases else None
    for project, spec in PROJECTS.items():
        if a.project and project != a.project:
            continue
        for mut in spec["mutations"]:
            if (wanted and mut["id"] not in wanted) or (mut["id"] in done and not a.dry):
                continue
            if a.dry:
                case = build(project, spec, mut)
                last = case.stderr.strip().splitlines()[-1]
                print(f"{mut['id']:10} ok  truth {case.truth_file}:{case.truth_line:<4} {last[:80]}")
                continue
            row = run_case(project, spec, mut, baseline=not a.no_baseline)
            if a.rerun:
                rows = [r for r in load_results() if r["id"] != row["id"]] + [row]
                RESULTS.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            else:
                with RESULTS.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row) + "\n")
            t, b = row["traceroot"], row.get("baseline", {})
            print(f"{row['id']:10} {row['distance']:10} truth {row['truth']:22} | traceroot {t['source']:8} "
                  f"rank {t['hit_rank'] or 'miss':<4} {t['model_tokens']:>6} tok | baseline rank "
                  f"{b.get('hit_rank') or 'miss':<4} {b.get('model_tokens', 0):>6} tok", flush=True)
    if not a.dry:
        SUMMARY.write_text(summarize(load_results()), encoding="utf-8")
        print(f"\nwrote {SUMMARY}")


if __name__ == "__main__":
    main()
