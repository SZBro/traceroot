"""Class-level statistics."""
import statistics
from collections import Counter

from . import policy
from .models import Course

AT_RISK_BELOW = 70.0


def all_percents(course: Course) -> dict[str, float]:
    return {sid: policy.final_percent(course, sid) for sid in course.students}


def summary(percents: dict[str, float]) -> dict[str, float]:
    values = list(percents.values())
    return {
        "mean": round(statistics.mean(values), 2),
        "median": round(statistics.median(values), 2),
        "stdev": round(statistics.pstdev(values), 2),
        "min": min(values),
        "max": max(values),
    }


def distribution(percents: dict[str, float]) -> Counter:
    return Counter(policy.letter_grade(p, policy.CUTOFFS) for p in percents.values())


def at_risk(course: Course, percents: dict[str, float]) -> list[tuple[str, float]]:
    rows = []
    for sid, pct in percents.items():
        if pct < AT_RISK_BELOW:
            student = course.find_student(sid)
            rows.append((student.full_name, pct))
    return sorted(rows, key=lambda r: r[1])


def assignment_difficulty(course: Course) -> list[tuple[str, float]]:
    rows = []
    for aid, a in course.assignments.items():
        subs = course.submissions_of(aid)
        if not subs:
            continue
        avg = statistics.mean(100.0 * s.points / a.max_points for s in subs)
        rows.append((aid, round(avg, 1)))
    return sorted(rows, key=lambda r: r[1])


def late_rate(course: Course) -> float:
    late = 0
    for sub in course.submissions:
        a = course.find_assignment(sub.assignment_id)
        if a and a.days_late(sub.submitted) > 0:
            late += 1
    return late / len(course.submissions) if course.submissions else 0.0


def section_means(course: Course, percents: dict[str, float]) -> dict[str, float]:
    groups: dict[str, list[float]] = {}
    for sid, pct in percents.items():
        groups.setdefault(course.students[sid].section, []).append(pct)
    return {name: round(statistics.mean(vals), 2) for name, vals in sorted(groups.items())}
