"""Grading policy: category weights, drop-lowest, late penalties, letter grades."""
from .models import Assignment, Course, Submission

WEIGHTS = {
    "homework": 0.25,
    "quiz": 0.10,
    "lab": 0.15,
    "exam": 0.30,
    "project": 0.20,
}

DROP_LOWEST = {
    "homework": 1,
    "quiz": 1,
    "lab": 0,
}

LATE_PENALTY_PER_DAY = 0.10
MAX_LATE_PENALTY = 0.50
GRACE_DAYS = 0

CUTOFFS = [
    (93.0, "A"), (90.0, "A-"), (87.0, "B+"), (83.0, "B"), (80.0, "B-"),
    (77.0, "C+"), (73.0, "C"), (70.0, "C-"), (60.0, "D"), (0.0, "F"),
]


def late_penalty(days_late: int) -> float:
    if days_late <= GRACE_DAYS:
        return 0.0
    return min(MAX_LATE_PENALTY, (days_late - GRACE_DAYS) * LATE_PENALTY_PER_DAY)


def adjusted_points(sub: Submission, assignment: Assignment) -> float:
    penalty = late_penalty(assignment.days_late(sub.submitted))
    return sub.points * (1 - penalty)


def percent(sub: Submission, assignment: Assignment) -> float:
    return 100.0 * adjusted_points(sub, assignment) / assignment.max_points


def category_scores(course: Course, student_id: str, category: str) -> list[float]:
    scores = []
    by_id = {s.assignment_id: s for s in course.submissions_for(student_id)}
    for a in course.assignments.values():
        if a.category != category:
            continue
        sub = by_id.get(a.assignment_id)
        scores.append(percent(sub, a) if sub else 0.0)
    return scores


def category_average(course: Course, student_id: str, category: str) -> float:
    scores = sorted(category_scores(course, student_id, category))
    drop = DROP_LOWEST.get(category, 0)
    kept = scores[drop:]
    if not kept:
        return 0.0
    return sum(kept) / len(kept)


def final_percent(course: Course, student_id: str) -> float:
    total = 0.0
    for category in course.categories():
        total += WEIGHTS[category] * category_average(course, student_id, category)
    return round(total, 2)


def letter_grade(pct: float, cutoffs: list[tuple[float, str]]) -> str:
    for minimum, letter in cutoffs:
        if pct >= minimum:
            return letter
    return cutoffs[-1][1]


def curve(percents: dict[str, float], target_mean: float) -> dict[str, float]:
    if not percents:
        return {}
    shift = target_mean - sum(percents.values()) / len(percents)
    return {sid: min(100.0, p + max(0.0, shift)) for sid, p in percents.items()}


def missing_work(course: Course, student_id: str) -> list[str]:
    done = {s.assignment_id for s in course.submissions_for(student_id)}
    return sorted(a for a in course.assignments if a not in done)
