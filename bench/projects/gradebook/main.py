from pathlib import Path

from grades import analytics, render
from grades.loader import load_course, validate

DATA = Path(__file__).resolve().parent / "data"


def class_report(course) -> str:
    percents = analytics.all_percents(course)
    parts = [
        render.heading(f"{course.code} roster"),
        render.roster_table(course, percents),
        render.heading("Summary"),
        render.summary_block(analytics.summary(percents)),
        render.distribution_block(analytics.distribution(percents)),
        f"Section means: {analytics.section_means(course, percents)}",
        f"Late submissions: {analytics.late_rate(course):.0%}",
        render.heading("At risk"),
        render.ranked_rows(analytics.at_risk(course, percents)),
        render.heading("Hardest assignments"),
        render.ranked_rows(analytics.assignment_difficulty(course)[:3]),
    ]
    return "\n".join(parts)


def main() -> None:
    course = load_course("TCSS-142", DATA)
    problems = validate(course)
    if problems:
        print("Data problems:\n  " + "\n  ".join(problems))
    print(class_report(course))
    first = course.roster()[0]
    print(render.heading("Sample transcript"))
    print(render.transcript(course, first.student_id))


if __name__ == "__main__":
    main()
