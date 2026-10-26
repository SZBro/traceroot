"""Text output: task table, Gantt chart, workload."""
from datetime import date

GANTT_WIDTH = 48
HIGH_PRIORITY = 1


def task_table(project, order, dates, slack) -> str:
    lines = [f"{'id':<5} {'task':<22} {'owner':<6} {'days':>4} {'start':>10} {'end':>10} {'slack':>5}"]
    for tid in order:
        t = project.get(tid)
        first, last = dates[tid]
        flag = "!" if t.priority <= HIGH_PRIORITY else " "
        lines.append(f"{tid:<5} {t.name:<22} {t.owner:<6} {t.duration:>4} {first:%m-%d}".ljust(51)
                     + f" {last:%m-%d}".rjust(11) + f" {slack[tid]:>5}{flag}")
    return "\n".join(lines)


def gantt(order, dates) -> str:
    start = min(d[0] for d in dates.values())
    end = max(d[1] for d in dates.values())
    span = max(1, (end - start).days)
    scale = GANTT_WIDTH / span
    rows = []
    for tid in order:
        first, last = dates[tid]
        left = int((first - start).days * scale)
        width = max(1, int(((last - first).days + 1) * scale))
        rows.append(f"{tid:<5}|{' ' * left}{'=' * width}")
    return "\n".join(rows)


def workload_table(load: dict[date, dict[str, int]], owners: list[str]) -> str:
    head = "week of   " + " ".join(f"{o:>5}" for o in owners)
    rows = [head]
    for week, per_owner in load.items():
        cells = " ".join(f"{per_owner.get(o, 0):>5}" for o in owners)
        rows.append(f"{week:%Y-%m-%d} {cells}")
    return "\n".join(rows)


def path_line(path: list[str]) -> str:
    return " -> ".join(path)


def levels_block(levels: list[list[str]]) -> str:
    return "\n".join(f"  stage {i + 1}: {', '.join(ids)}" for i, ids in enumerate(levels))
