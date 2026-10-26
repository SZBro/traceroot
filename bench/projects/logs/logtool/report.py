"""Text report formatting."""
from .settings import COLUMN_WIDTHS, THRESHOLDS
from .stats import RouteStats


def human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def status_level(rate: float) -> str:
    if rate >= THRESHOLDS["error_rate_alert"]:
        return "ALERT"
    if rate >= THRESHOLDS["error_rate_warn"]:
        return "warn"
    return "ok"


def bar(count: int, total: int, width: int = 30) -> str:
    filled = round(width * count / total) if total else 0
    return "#" * filled + "." * (width - filled)


def section(title: str) -> str:
    return f"\n{title}\n{'-' * len(title)}"


def route_table(rows: list[RouteStats]) -> str:
    w = COLUMN_WIDTHS
    head = f"{'route':<{w['path']}} {'count':>{w['count']}} {'p50':>{w['ms']}} {'p90':>{w['ms']}} errors"
    lines = [head]
    for s in rows:
        lines.append(f"{s.route:<{w['path']}} {s.count:>{w['count']}} {s.p50:>{w['ms']}.0f} "
                     f"{s.p90:>{w['ms']}.0f} {s.errors} ({status_level(s.error_rate)})")
    return "\n".join(lines)


def histogram_block(hist: list[tuple[str, int]]) -> str:
    total = sum(c for _, c in hist)
    return "\n".join(f"{label:>9} {bar(count, total)} {count}" for label, count in hist)


def ranked(items: list[tuple[str, int]]) -> str:
    return "\n".join(f"{i}. {name} ({count})" for i, (name, count) in enumerate(items, 1))


def latency_line(summary: dict[int, float]) -> str:
    return "  ".join(f"p{p}={v:.0f}ms" for p, v in sorted(summary.items()))


def slow_block(records, limit: int = 5) -> str:
    rows = [f"{r.ms:>6}ms {r.method:<5} {r.route}" for r in records[:limit]]
    return "\n".join(rows) if rows else "(none)"
