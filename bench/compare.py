"""Compare two benchmark result files case by case (e.g. TraceRoot v4 vs v5 on the same cases).

    python bench/compare.py bench/versions/v4_results.jsonl bench/out/results_v5_known.jsonl
"""
import json
import sys
from pathlib import Path


def load(path: str) -> dict[str, dict]:
    rows = [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]
    return {r["id"]: r for r in rows}


def avg(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def stats(rows: list[dict]) -> dict:
    t = [r["traceroot"] for r in rows]
    gate = [x for x in t if x["source"] == "jev_gate"]
    full = [x for x in t if x["source"] == "full"]
    return {
        "cases": len(t),
        "top-1": sum(x["top1"] for x in t),
        "top-3": sum(bool(x["hit_rank"]) and x["hit_rank"] <= 3 for x in t),
        "shown up front": sum(x.get("shown_hit", x["top1"]) for x in t),
        "gate answered": len(gate),
        "gate correct": sum(x["top1"] for x in gate),
        "full-path top-1": sum(x["top1"] for x in full),
        "avg model tokens": round(avg(x["model_tokens"] for x in t)),
        "  gate path": round(avg(x["model_tokens"] for x in gate)),
        "  full path": round(avg(x["model_tokens"] for x in full)),
        "  Jev tokens (full)": round(avg(x["jev_tokens"] for x in full)),
        "  Claude tokens (full)": round(avg(x["claude_tokens"] for x in full)),
        "agent context tokens": round(avg(x["returned_tokens"] for x in t)),
        "avg latency s": round(avg(x["latency_ms"] for x in t) / 1000, 1),
    }


def main(a: str, b: str) -> None:
    ra, rb = load(a), load(b)
    ids = [i for i in ra if i in rb]
    sa, sb = stats([ra[i] for i in ids]), stats([rb[i] for i in ids])
    base = [ra[i]["baseline"] for i in ids if "baseline" in ra[i]]
    print(f"{len(ids)} shared cases\n")
    print(f"| metric | {Path(a).stem} | {Path(b).stem} |\n|---|---|---|")
    for k in sa:
        print(f"| {k} | {sa[k]} | {sb[k]} |")
    if base:
        print(f"\nbaseline (same cases): top-1 {sum(x['top1'] for x in base)}/{len(base)}, "
              f"avg model tokens {round(avg(x['model_tokens'] for x in base))}")
    changed = [(i, ra[i]["traceroot"], rb[i]["traceroot"]) for i in ids
               if ra[i]["traceroot"]["hit_rank"] != rb[i]["traceroot"]["hit_rank"]
               or ra[i]["traceroot"]["source"] != rb[i]["traceroot"]["source"]]
    if changed:
        print("\ncases that changed (hit rank / path):")
        for i, x, y in changed:
            print(f"  {i:9} {x['source']:8} rank {x['hit_rank'] or 'miss'}  ->  {y['source']:8} rank {y['hit_rank'] or 'miss'}"
                  f"{'  (shown via alt)' if y.get('shown_hit') and not y['top1'] else ''}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
