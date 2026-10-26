"""Text output: roster table, transcripts, class report."""
from . import policy
from .models import Course

NAME_WIDTH = 22


def pct_cell(value: float) -> str:
    return f"{value:6.2f}%"


def roster_table(course: Course, percents: dict[str, float]) -> str:
    lines = [f"{'student':<{NAME_WIDTH}} {'id':<6} {'sec':<4} {'final':>8} grade"]
    for s in course.roster():
        pct = percents[s.student_id]
        grade = policy.letter_grade(pct, policy.CUTOFFS)
        lines.append(f"{s.full_name:<{NAME_WIDTH}} {s.student_id:<6} {s.section:<4} {pct_cell(pct):>8} {grade}")
    return "\n".join(lines)


def transcript(course: Course, student_id: str) -> str:
    student = course.find_student(student_id)
    lines = [f"Transcript: {student.full_name} ({student_id})"]
    for category in course.categories():
        avg = policy.category_average(course, student_id, category)
        weight = policy.WEIGHTS[category]
        lines.append(f"  {category:<10} {pct_cell(avg)}  x {weight:.2f}")
    final = policy.final_percent(course, student_id)
    lines.append(f"  {'final':<10} {pct_cell(final)}  {policy.letter_grade(final, policy.CUTOFFS)}")
    missing = policy.missing_work(course, student_id)
    if missing:
        lines.append(f"  missing: {', '.join(missing)}")
    return "\n".join(lines)


def distribution_block(dist) -> str:
    order = [letter for _, letter in policy.CUTOFFS]
    return "  ".join(f"{letter}:{dist.get(letter, 0)}" for letter in order if dist.get(letter, 0))


def summary_block(stats: dict[str, float]) -> str:
    return "  ".join(f"{k}={v}" for k, v in stats.items())


def ranked_rows(rows: list[tuple[str, float]], suffix: str = "%") -> str:
    if not rows:
        return "  (none)"
    return "\n".join(f"  {name:<{NAME_WIDTH}} {value:6.1f}{suffix}" for name, value in rows)


def heading(text: str) -> str:
    return f"\n== {text} =="
