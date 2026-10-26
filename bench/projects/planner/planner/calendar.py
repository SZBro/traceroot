"""Turn working-day offsets into calendar dates."""
from datetime import date, timedelta

HOLIDAYS = {
    date(2026, 11, 11),
    date(2026, 11, 26),
    date(2026, 11, 27),
    date(2026, 12, 25),
}

WORKDAYS = {0, 1, 2, 3, 4}


def is_workday(day: date) -> bool:
    return day.weekday() in WORKDAYS and day not in HOLIDAYS


def next_workday(day: date) -> date:
    while not is_workday(day):
        day += timedelta(days=1)
    return day


def add_workdays(start: date, n: int) -> date:
    day = next_workday(start)
    remaining = n
    while remaining > 0:
        day += timedelta(days=1)
        if is_workday(day):
            remaining -= 1
    return day


def assign_dates(project, earliest: dict[str, int], finish: dict[str, int], start: date) -> dict[str, tuple[date, date]]:
    dates = {}
    for tid in earliest:
        first = add_workdays(start, earliest[tid])
        last = add_workdays(start, finish[tid] - 1)
        dates[tid] = (first, last)
    return dates


def week_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def workload_by_week(project, dates: dict[str, tuple[date, date]]) -> dict[date, dict[str, int]]:
    load: dict[date, dict[str, int]] = {}
    for tid, (first, last) in dates.items():
        owner = project.get(tid).owner
        day = first
        while day <= last:
            if is_workday(day):
                load.setdefault(week_of(day), {}).setdefault(owner, 0)
                load[week_of(day)][owner] += 1
            day += timedelta(days=1)
    return dict(sorted(load.items()))
