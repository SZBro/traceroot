"""Parse access-log lines (combined format plus a trailing response time in ms)."""
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LINE_RE = re.compile(
    r'(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] '
    r'"(?P<method>[A-Z]+) (?P<path>\S+) (?P<proto>[^"]+)" '
    r'(?P<status>\d{3}) (?P<size>\d+) (?P<ms>\d+) "(?P<agent>[^"]*)"'
)

TIME_FORMAT = "%d/%b/%Y:%H:%M:%S %z"


@dataclass
class Record:
    ip: str
    time: datetime
    method: str
    path: str
    status: int
    size: int
    ms: int
    agent: str

    @property
    def route(self) -> str:
        return self.path.split("?", 1)[0]

    @property
    def is_error(self) -> bool:
        return self.status >= 500

    @property
    def is_client_error(self) -> bool:
        return 400 <= self.status < 500


class ParseError(ValueError):
    pass


def parse_time(text: str) -> datetime:
    return datetime.strptime(text, TIME_FORMAT)


def parse_line(line: str) -> Record | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    m = LINE_RE.match(line)
    if not m:
        raise ParseError(f"unrecognized log line: {line[:60]}")
    return Record(
        ip=m["ip"],
        time=parse_time(m["time"]),
        method=m["method"],
        path=m["path"],
        status=int(m["status"]),
        size=int(m["size"]),
        ms=int(m["ms"]),
        agent=m["agent"],
    )


def load_records(path: Path) -> list[Record]:
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    records = [r for r in (parse_line(line) for line in lines) if r]
    return records


def split_by_hour(records: list[Record]) -> dict[int, list[Record]]:
    hours: dict[int, list[Record]] = {}
    for r in records:
        hours.setdefault(r.time.hour, []).append(r)
    return hours


def time_span(records: list[Record]) -> tuple[datetime, datetime]:
    times = sorted(r.time for r in records)
    return times[0], times[-1]
