"""Dependency graph: ordering, earliest times, critical path, slack."""
from collections import deque

from .model import Project


class CycleError(ValueError):
    pass


def topo_order(project: Project) -> list[str]:
    indegree = {tid: 0 for tid in project.tasks}
    for t in project.tasks.values():
        for _ in t.deps:
            indegree[t.id] += 1
    ready = deque(sorted(tid for tid, n in indegree.items() if n == 0))
    order = []
    while ready:
        tid = ready.popleft()
        order.append(tid)
        for child in sorted(project.dependents(tid), key=lambda t: t.id):
            indegree[child.id] -= 1
            if indegree[child.id] == 0:
                ready.append(child.id)
    if len(order) != len(project.tasks):
        raise CycleError("dependency cycle among: " + ", ".join(sorted(set(project.tasks) - set(order))))
    return order


def earliest_times(project: Project, order: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    earliest, finish = {}, {}
    for tid in order:
        task = project.get(tid)
        earliest[tid] = max((finish[d] for d in task.deps), default=0)
        finish[tid] = earliest[tid] + task.duration
    return earliest, finish


def latest_times(project: Project, order: list[str], end: int) -> dict[str, int]:
    latest_finish = {}
    for tid in reversed(order):
        kids = project.dependents(tid)
        if not kids:
            latest_finish[tid] = end
        else:
            latest_finish[tid] = min(latest_finish[k.id] - k.duration for k in kids)
    return latest_finish


def slack(project: Project, order: list[str]) -> dict[str, int]:
    _, finish = earliest_times(project, order)
    end = max(finish.values())
    latest = latest_times(project, order, end)
    return {tid: latest[tid] - finish[tid] for tid in order}


def critical_path(project: Project, order: list[str]) -> list[str]:
    _, finish = earliest_times(project, order)
    path = []
    current = max(finish, key=finish.get)
    while current:
        path.append(current)
        task = project.get(current)
        if not task.deps:
            break
        current = max(task.deps, key=lambda d: finish[d])
    return list(reversed(path))


def levels(project: Project, order: list[str]) -> list[list[str]]:
    depth = {}
    for tid in order:
        task = project.get(tid)
        depth[tid] = 1 + max((depth[d] for d in task.deps), default=-1)
    rows: list[list[str]] = [[] for _ in range(max(depth.values()) + 1)]
    for tid in order:
        rows[depth[tid]].append(tid)
    return rows
