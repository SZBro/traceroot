"""Record filters used before computing stats."""
from .parser import Record
from .settings import BOT_MARKERS, STATIC_PREFIXES


def is_static(record: Record) -> bool:
    return record.route.startswith(STATIC_PREFIXES)


def is_bot(record: Record) -> bool:
    agent = record.agent.lower()
    return any(marker in agent for marker in BOT_MARKERS)


def only_api(records: list[Record]) -> list[Record]:
    return [r for r in records if r.route.startswith("/api/")]


def exclude_static(records: list[Record]) -> list[Record]:
    return [r for r in records if not is_static(r)]


def exclude_bots(records: list[Record]) -> list[Record]:
    return [r for r in records if not is_bot(r)]


def by_method(records: list[Record], method: str) -> list[Record]:
    method = method.upper()
    return [r for r in records if r.method == method]


def by_status_class(records: list[Record], klass: int) -> list[Record]:
    return [r for r in records if r.status // 100 == klass]


def between_hours(records: list[Record], start: int, end: int) -> list[Record]:
    return [r for r in records if start <= r.time.hour < end]


def clean(records: list[Record]) -> list[Record]:
    return exclude_bots(exclude_static(records))
