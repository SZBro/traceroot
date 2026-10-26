"""Aggregate statistics over parsed records."""
from collections import Counter
from dataclasses import dataclass

from .parser import Record
from .settings import HISTOGRAM_BUCKETS_MS, PERCENTILES, THRESHOLDS


@dataclass
class RouteStats:
    route: str
    count: int
    errors: int
    p50: float
    p90: float
    p99: float

    @property
    def error_rate(self) -> float:
        return self.errors / self.count if self.count else 0.0


def _rank_index(n: int, p: float) -> int:
    return int(round(p / 100 * (n - 1)))


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[_rank_index(len(ordered), p)])


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def latency_summary(records: list[Record]) -> dict[int, float]:
    times = [r.ms for r in records]
    return {p: percentile(times, p) for p in PERCENTILES}


def error_rate(records: list[Record]) -> float:
    if not records:
        return 0.0
    return sum(r.is_error for r in records) / len(records)


def status_counts(records: list[Record]) -> Counter:
    return Counter(r.status for r in records)


def top_n(counter: Counter, n: int) -> list[tuple[str, int]]:
    return counter.most_common(n)


def busiest_routes(records: list[Record], n: int) -> list[tuple[str, int]]:
    return top_n(Counter(r.route for r in records), n)


def busiest_ips(records: list[Record], n: int) -> list[tuple[str, int]]:
    return top_n(Counter(r.ip for r in records), n)


def per_route(records: list[Record]) -> list[RouteStats]:
    groups: dict[str, list[Record]] = {}
    for r in records:
        groups.setdefault(r.route, []).append(r)
    out = []
    for route, rs in groups.items():
        times = [r.ms for r in rs]
        out.append(RouteStats(route=route, count=len(rs), errors=sum(r.is_error for r in rs),
                              p50=percentile(times, 50), p90=percentile(times, 90), p99=percentile(times, 99)))
    return sorted(out, key=lambda s: (-s.count, s.route))


def slow_requests(records: list[Record]) -> list[Record]:
    limit = THRESHOLDS["slow_ms"]
    return sorted((r for r in records if r.ms >= limit), key=lambda r: -r.ms)


def histogram(records: list[Record]) -> list[tuple[str, int]]:
    edges = list(HISTOGRAM_BUCKETS_MS)
    counts = [0] * (len(edges) + 1)
    for r in records:
        for i, edge in enumerate(edges):
            if r.ms < edge:
                counts[i] += 1
                break
        else:
            counts[-1] += 1
    labels = [f"<{e}ms" for e in edges] + [f">={edges[-1]}ms"]
    return list(zip(labels, counts))


def bytes_served(records: list[Record]) -> int:
    return sum(r.size for r in records)
