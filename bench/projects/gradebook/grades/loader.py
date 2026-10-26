"""Load the course from CSV exports and validate it."""
import csv
from datetime import date, datetime
from pathlib import Path

from .models import Assignment, Course, Student, Submission

DATE_FMT = "%Y-%m-%d"

REQUIRED_COLUMNS = {
    "students.csv": {"student_id", "first", "last", "section", "email"},
    "assignments.csv": {"assignment_id", "category", "max_points", "due"},
    "scores.csv": {"student_id", "assignment_id", "points", "submitted"},
}


class LoadError(Exception):
    pass


def parse_date(text: str) -> date:
    return datetime.strptime(text.strip(), DATE_FMT).date()


def read_rows(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_COLUMNS.get(path.name, set()) - set(reader.fieldnames or [])
        if missing:
            raise LoadError(f"{path.name} is missing columns: {', '.join(sorted(missing))}")
        return [row for row in reader if any(v.strip() for v in row.values())]


def student_from_row(row: dict[str, str]) -> Student:
    return Student(
        student_id=row["student_id"].strip(),
        first=row["first"].strip(),
        last=row["last"].strip(),
        section=row["section"].strip().upper(),
        email=row["email"].strip().lower(),
    )


def assignment_from_row(row: dict[str, str]) -> Assignment:
    return Assignment(
        assignment_id=row["assignment_id"].strip(),
        category=row["category"].strip().lower(),
        max_points=float(row["max_points"]),
        due=parse_date(row["due"]),
    )


def submission_from_row(row: dict[str, str]) -> Submission:
    return Submission(
        student_id=row["student_id"].strip(),
        assignment_id=row["assignment_id"].strip(),
        points=float(row["points"]),
        submitted=parse_date(row["submitted"]),
    )


def validate(course: Course) -> list[str]:
    problems = []
    for sub in course.submissions:
        if sub.student_id not in course.students:
            problems.append(f"score for unknown student {sub.student_id}")
        a = course.find_assignment(sub.assignment_id)
        if a is None:
            problems.append(f"score for unknown assignment {sub.assignment_id}")
        elif sub.points > a.max_points:
            problems.append(f"{sub.student_id} has {sub.points} > {a.max_points} on {a.assignment_id}")
    return problems


def load_course(code: str, folder: Path) -> Course:
    course = Course(code=code)
    for row in read_rows(folder / "students.csv"):
        course.add_student(student_from_row(row))
    for row in read_rows(folder / "assignments.csv"):
        course.add_assignment(assignment_from_row(row))
    course.submissions = [submission_from_row(row) for row in read_rows(folder / "scores.csv")]
    return course
