"""Write .traceroot/view.html: every cause ranked (Jev p and Claude confidence side by side) plus a
Mermaid diagram for one chosen cause. Claude draws the diagram; plain code builds everything else,
and draws a simple call-path diagram itself if Claude is unavailable or returns invalid Mermaid."""
import html
import re
import sys
import webbrowser
from pathlib import Path

from . import claude_client, config, store

MERMAID_SRC = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"
CLASS_DEFS = ("\n  classDef cause fill:#fde68a,stroke:#b45309,stroke-width:2px,color:#1c1917"
              "\n  classDef crash fill:#fecaca,stroke:#b91c1c,stroke-width:2px,color:#1c1917")


def _esc(v) -> str:
    return html.escape("" if v is None else str(v))


def _label(text: str) -> str:
    """Make text safe inside a Mermaid ["..."] label."""
    return re.sub(r'["\[\]{}<>|]', "'", text)[:70]


# ---------- diagram ----------

def clean_mermaid(text) -> str | None:
    """Accept only a flowchart; strip fences. Returns None when it doesn't look like Mermaid."""
    if not isinstance(text, str):
        return None
    text = re.sub(r"```(?:mermaid)?", "", text).strip()
    if not re.match(r"^(flowchart|graph)\s+(TD|TB|LR|BT|RL)\b", text):
        return None
    if re.search(r"<\s*script|javascript:|click\s", text, re.I):   # no interactivity / scripts
        return None
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("classDef")]
    return "\n".join(lines) + CLASS_DEFS


def fallback_mermaid(result: dict, cause: dict) -> str:
    """Code-built diagram: the call path from the traceback, with the cause attached."""
    frames = result.get("frames") or []
    lines = ["flowchart TD"]
    ids = []
    for i, f in enumerate(frames):
        nid = f"F{i}"
        ids.append(nid)
        cls = ":::crash" if i == len(frames) - 1 else ""
        lines.append(f'  {nid}["{_label(f"{f.get("func") or "?"}  {Path(f["file"]).name}:{f["line"]}")}"]{cls}')
    for a, b in zip(ids, ids[1:]):
        lines.append(f"  {a} --> {b}")
    if not ids:
        lines.append(f'  E["{_label(result.get("error_line") or "error")}"]:::crash')
        ids = ["E"]
    where = f"  {Path(cause['file']).name}:{cause['line']}" if cause.get("file") and cause.get("line") else ""
    lines.append(f'  C["{_label(cause["title"] + where)}"]:::cause')
    lines.append(f'  C -.->|"root cause"| {ids[-1]}')
    return "\n".join(lines) + CLASS_DEFS


def diagram_for(result: dict, idx: int) -> tuple[str, str]:
    """-> (mermaid, source) where source is 'claude', 'cached', or 'fallback'. Caches in last.json."""
    cause = result["causes"][idx]
    cached = (result.get("diagrams") or {}).get(cause["id"])
    if cached:
        return cached, "cached"
    frames = "\n".join(f"{i + 1}. {f.get('func')} at {f['file']}:{f['line']}"
                       for i, f in enumerate(result.get("frames") or [])) or "(no frames)"
    where = f"{cause['file']}:{cause['line']}" if cause.get("file") else "location unknown"
    cause_text = f"{cause['title']} ({where}). {cause.get('explanation') or ''}"
    try:
        data = claude_client.ask_claude(claude_client.diagram_prompt(
            result.get("error_line") or "", frames, cause_text, result.get("slices_text") or ""))
        data.pop("_meta", None)
        mermaid = clean_mermaid(data.get("mermaid"))
        if mermaid is None:
            raise claude_client.ClaudeError("Claude's diagram was not a valid flowchart")
        source = "claude"
    except claude_client.ClaudeError as e:
        print(f"traceroot: {e}; using a code-built call-path diagram", file=sys.stderr)
        return fallback_mermaid(result, cause), "fallback"
    result.setdefault("diagrams", {})[cause["id"]] = mermaid
    store.update(result)
    return mermaid, source


# ---------- page ----------

def _pct(p) -> str:
    return "–" if p is None else f"{p:.2f}"


def _rows(result: dict, chosen: int) -> str:
    causes = result["causes"]
    by_claude = {c["id"]: c.get("claude_rank") for c in causes}
    jev_sorted = sorted((c for c in causes if c.get("jev_p") is not None), key=lambda c: -c["jev_p"])
    by_jev = {c["id"]: i + 1 for i, c in enumerate(jev_sorted)}
    out = []
    for i, c in enumerate(causes):
        cr, jr = by_claude.get(c["id"]), by_jev.get(c["id"])
        if cr and jr:
            agree = '<span class="tag ok" title="same rank from both models">agree</span>' if cr == jr \
                else f'<span class="tag warn" title="ranked differently">Claude #{cr} · Jev #{jr}</span>'
        else:
            agree = '<span class="tag">one model</span>'
        where = f"{_esc(c['file'])}:{_esc(c['line'])}" if c.get("file") and c.get("line") else \
            _esc(c.get("file") or "–")
        bar = "" if c.get("jev_p") is None else f'<span class="bar" style="width:{c["jev_p"] * 100:.0f}%"></span>'
        out.append(f"""
      <article class="cause{' chosen' if i == chosen else ''}">
        <header>
          <span class="rank">#{i + 1}</span>
          <h3>{_esc(c['title'])}</h3>
          {agree}
        </header>
        <div class="meta">
          <span class="cat">{_esc(c['category'])}</span>
          <code>{where}</code>
          <span class="score" title="Jev probability">Jev p <b>{_pct(c.get('jev_p'))}</b><span class="track">{bar}</span></span>
          <span class="score" title="Claude's own confidence">Claude <b>{_pct(c.get('claude_confidence'))}</b></span>
        </div>
        <p>{_esc(c.get('explanation'))}</p>
        <p class="fix"><b>Fix:</b> {_esc(c.get('fix_hint'))}</p>
        {'' if i == chosen else f'<p class="hint">Diagram: <code>traceroot view {i + 1}</code></p>'}
      </article>""")
    return "".join(out)


def build_page(result: dict, chosen: int, mermaid: str, diagram_source: str) -> str:
    gate = result.get("gate") or {}
    path_label = {"jev_gate": "answered by the Jev gate alone", "full": "Claude candidates, scored by Jev",
                  "fallback": "model unavailable: crash site only"}.get(result.get("source"), result.get("source"))
    gate_txt = f"{_esc(gate.get('category'))} (p={gate.get('probability', 0):.2f})" if gate else "unavailable"
    meta = result.get("meta") or {}
    diagram_note = {"claude": "drawn by Claude", "cached": "drawn by Claude (cached)",
                    "fallback": "code-built call path (Claude unavailable)"}[diagram_source]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TraceRoot View</title>
<style>
  :root {{
    --bg: #f7f7f5; --panel: #ffffff; --ink: #1c1917; --muted: #6b6560; --line: #e4e2dd;
    --accent: #b45309; --accent-soft: #fef3c7; --ok: #15803d; --ok-soft: #dcfce7;
    --warn: #b91c1c; --warn-soft: #fee2e2; --code: #f1f0ec;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #161514; --panel: #1f1e1c; --ink: #ecebe8; --muted: #a39e98; --line: #34322f;
      --accent: #f59e0b; --accent-soft: #3b2a10; --ok: #4ade80; --ok-soft: #12301d;
      --warn: #f87171; --warn-soft: #3a1717; --code: #2a2926;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink);
         font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }}
  main {{ max-width: 980px; margin: 0 auto; padding: 28px 16px 60px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  h2 {{ font-size: 15px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 32px 0 12px; }}
  code, pre {{ font: 13px/1.5 ui-monospace, "Cascadia Mono", Consolas, monospace; }}
  .error {{ background: var(--warn-soft); color: var(--warn); padding: 10px 14px; border-radius: 8px;
           overflow-wrap: anywhere; margin: 12px 0; }}
  .facts {{ display: flex; flex-wrap: wrap; gap: 8px 20px; color: var(--muted); font-size: 13px; }}
  .facts b {{ color: var(--ink); font-weight: 600; }}
  .cause {{ background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
           padding: 14px 16px; margin-bottom: 10px; }}
  .cause.chosen {{ border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }}
  .cause header {{ display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }}
  .cause h3 {{ margin: 0; font-size: 16px; flex: 1 1 260px; }}
  .rank {{ font-weight: 700; color: var(--accent); }}
  .cause p {{ margin: 8px 0 0; }}
  .fix {{ color: var(--ink); }}
  .hint {{ color: var(--muted); font-size: 13px; }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: center; margin-top: 6px;
          font-size: 13px; color: var(--muted); }}
  .meta code {{ background: var(--code); padding: 1px 6px; border-radius: 4px; overflow-wrap: anywhere; }}
  .cat {{ background: var(--accent-soft); color: var(--accent); padding: 1px 8px; border-radius: 999px; }}
  .score b {{ color: var(--ink); font-variant-numeric: tabular-nums; }}
  .track {{ display: inline-block; width: 60px; height: 6px; background: var(--line); border-radius: 3px;
           margin-left: 6px; vertical-align: middle; overflow: hidden; }}
  .bar {{ display: block; height: 100%; background: var(--accent); }}
  .tag {{ font-size: 12px; padding: 1px 8px; border-radius: 999px; background: var(--code); color: var(--muted); }}
  .tag.ok {{ background: var(--ok-soft); color: var(--ok); }}
  .tag.warn {{ background: var(--warn-soft); color: var(--warn); }}
  .diagram {{ background: #ffffff; border: 1px solid var(--line); border-radius: 10px; padding: 16px;
             overflow-x: auto; }}
  .diagram .mermaid {{ display: flex; justify-content: center; margin: 0; }}
  .note {{ color: var(--muted); font-size: 13px; margin-top: 6px; }}
  details {{ background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px; }}
  details pre {{ background: var(--code); padding: 12px; border-radius: 6px; overflow-x: auto; }}
  summary {{ cursor: pointer; color: var(--muted); }}
</style>
</head>
<body>
<main>
  <h1>TraceRoot</h1>
  <div class="error"><code>{_esc(result.get('error_line'))}</code></div>
  <div class="facts">
    <span>Path: <b>{_esc(path_label)}</b></span>
    <span>Jev gate: <b>{gate_txt}</b></span>
    <span>Ranked by: <b>{_esc(result.get('order_by'))}</b></span>
    <span>Claude tokens: <b>{meta.get('claude_tokens', 0)}</b> · Jev tokens: <b>{meta.get('jev_tokens', 0)}</b></span>
    <span>{_esc(result.get('timestamp'))}</span>
  </div>

  <h2>Diagram for cause #{chosen + 1}</h2>
  <div class="diagram"><pre class="mermaid">{_esc(mermaid)}</pre></div>
  <p class="note">{diagram_note}. Yellow = root cause, red = crash.</p>

  <h2>Ranked causes ({len(result['causes'])})</h2>
  {_rows(result, chosen)}

  <h2>Code sent to the models</h2>
  <details><summary>Show code slices (lines marked &gt;&gt; are traceback frames)</summary>
    <pre>{_esc(result.get('slices_text'))}</pre>
  </details>
</main>
<script src="{MERMAID_SRC}"></script>
<script>mermaid.initialize({{ startOnLoad: true, securityLevel: "strict", theme: "default" }});</script>
</body>
</html>
"""


def render(n: int = 1, open_browser: bool = True) -> Path | None:
    result = store.load()
    if not result or not result.get("causes"):
        print("traceroot: nothing saved yet; run `traceroot analyze` first")
        return None
    total = len(result["causes"])
    if not 1 <= n <= total:
        print(f"traceroot: cause {n} does not exist (there are {total})")
        return None
    mermaid, source = diagram_for(result, n - 1)
    out = config.STATE_DIR / "view.html"
    out.write_text(build_page(result, n - 1, mermaid, source), encoding="utf-8")
    print(f"traceroot: wrote {out} (diagram: {source})")
    if open_browser:
        webbrowser.open(out.resolve().as_uri())
    return out
