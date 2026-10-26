"""Run only the Jev gate on every saved traceback (1 Jev call each, no Claude) and print a table.
Used to tune GATE_THRESHOLD.  python tests/fixtures/gate_report.py   (from the TraceRoot folder)"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from traceroot import config, jev_client, pipeline, trace_parser  # noqa: E402
from run_all import FIXTURES  # noqa: E402

# Should the gate answer alone? Only when the root cause is on the crash line.
GATE_SHOULD_ANSWER = {"easy_missing_import", "easy_typo_name", "easy_file_not_found", "easy_wrong_args"}

print(f"{'fixture':22} {'expected':26} {'gate pick':26} {'p':>5}  {'top-2':>5}  ok?   tokens  ms")
for name, (expected, _) in FIXTURES.items():
    stem = Path(name).stem
    parsed = trace_parser.parse((ROOT / "tests/fixtures/tracebacks" / f"{stem}.txt").read_text(), ROOT)
    t = time.perf_counter()
    before = jev_client.last_usage["input_tokens"]
    g = jev_client.gate(pipeline.traceback_text(parsed), pipeline.slices_text(parsed))
    ms = int((time.perf_counter() - t) * 1000)
    if g is None:
        print(f"{stem:22} gate unavailable")
        continue
    second = sorted(g["probabilities"].values(), reverse=True)[1]
    want = "easy" if stem in GATE_SHOULD_ANSWER else "full"
    print(f"{stem:22} {expected:26} {g['category']:26} {g['probability']:5.2f}  {second:5.2f}  "
          f"{want:4}  {jev_client.last_usage['input_tokens'] - before:6}  {ms}")
print(f"\nthreshold now: {config.GATE_THRESHOLD}")
