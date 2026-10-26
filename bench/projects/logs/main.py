from pathlib import Path

from logtool import filters, report, stats
from logtool.parser import load_records, split_by_hour, time_span
from logtool.settings import TOP_N

LOG = Path(__file__).resolve().parent / "data" / "access.log"


def overview(records) -> str:
    start, end = time_span(records)
    rate = stats.error_rate(records)
    lines = [
        f"Requests: {len(records)}  ({start:%H:%M} - {end:%H:%M})",
        f"Served:   {report.human_bytes(stats.bytes_served(records))}",
        f"Errors:   {rate:.1%} ({report.status_level(rate)})",
        f"Latency:  {report.latency_line(stats.latency_summary(records))}",
    ]
    return "\n".join(lines)


def hourly(records) -> str:
    rows = []
    for hour, rs in sorted(split_by_hour(records).items()):
        rows.append(f"{hour:02d}:00  {len(rs):>4} req  {stats.error_rate(rs):>6.1%} errors")
    return "\n".join(rows)


def build_report(records) -> str:
    api = filters.clean(filters.only_api(records))
    parts = [
        overview(records),
        report.section("Busiest routes"),
        report.ranked(stats.busiest_routes(records, TOP_N)),
        report.section("API routes"),
        report.route_table(stats.per_route(api)),
        report.section("Latency histogram"),
        report.histogram_block(stats.histogram(records)),
        report.section("Slowest requests"),
        report.slow_block(stats.slow_requests(records)),
        report.section("By hour"),
        hourly(records),
        report.section("Top clients"),
        report.ranked(stats.busiest_ips(records, TOP_N)),
    ]
    return "\n".join(parts)


def main() -> None:
    records = load_records(LOG)
    print(build_report(records))


if __name__ == "__main__":
    main()
