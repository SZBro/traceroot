"""Core data types for the gradebook."""
from dataclasses import dataclass, field
from datetime import date


@dataclass
class Student:
    student_id: str
    first: str
    last: str
    section: str
    email: str

    @property
    def full_name(self) -> str:
        return f"{self.first} {self.last}"

    @property
    def sort_key(self) -> tuple[str, str]:
        return (self.last.lower(), self.first.lower())

    def initials(self) -> str:
        return f"{self.first[:1]}{self.last[:1]}".upper()


@dataclass
class Assignment:
    assignment_id: str
    category: str
    max_points: float
    due: date

    def days_late(self, submitted: date) -> int:
        return (submitted - self.due).days


@dataclass
class Submission:
    student_id: str
    assignment_id: str
    points: float
    submitted: date


@dataclass
class Course:
    code: str
    students: dict[str, Student] = field(default_factory=dict)
    assignments: dict[str, Assignment] = field(default_factory=dict)
    submissions: list[Submission] = field(default_factory=list)

    def add_student(self, student: Student) -> None:
        if student.student_id in self.students:
            raise ValueError(f"duplicate student id {student.student_id}")
        self.students[student.student_id] = student

    def add_assignment(self, assignment: Assignment) -> None:
        self.assignments[assignment.assignment_id] = assignment

    def find_student(self, student_id: str) -> Student | None:
        return self.students.get(student_id)

    def find_assignment(self, assignment_id: str) -> Assignment | None:
        return self.assignments.get(assignment_id)

    def submissions_for(self, student_id: str) -> list[Submission]:
        return [s for s in self.submissions if s.student_id == student_id]

    def submissions_of(self, assignment_id: str) -> list[Submission]:
        return [s for s in self.submissions if s.assignment_id == assignment_id]

    def categories(self) -> list[str]:
        return sorted({a.category for a in self.assignments.values()})

    def roster(self) -> list[Student]:
        return sorted(self.students.values(), key=lambda s: s.sort_key)

    def section(self, name: str) -> list[Student]:
        return [s for s in self.roster() if s.section == name]
