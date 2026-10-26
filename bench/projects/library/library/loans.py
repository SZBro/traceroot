"""Checkouts, returns, due dates and fines."""
from dataclasses import dataclass
from datetime import date, timedelta

from .catalog import Book, normalize_isbn
from .members import MemberDirectory, can_borrow, loan_days

FINE_PER_DAY = 0.25
MAX_FINE = 10.00
GRACE_DAYS = 2


class LoanError(Exception):
    pass


@dataclass
class Loan:
    isbn: str
    member_id: str
    out: date
    due: date
    returned: date | None = None

    def days_late(self, today: date) -> int:
        end = self.returned or today
        return max(0, (end - self.due).days)


def fine_for(loan: Loan, today: date) -> float:
    late = loan.days_late(today) - GRACE_DAYS
    if late <= 0:
        return 0.0
    return min(MAX_FINE, late * FINE_PER_DAY)


class LoanBook:
    def __init__(self, books: dict[str, Book], members: MemberDirectory):
        self.books = books
        self.members = members
        self.loans: list[Loan] = []

    def out_count(self, isbn: str) -> int:
        return sum(1 for loan in self.loans if loan.isbn == isbn and loan.returned is None)

    def available(self, isbn: str) -> int:
        return self.books[isbn].copies - self.out_count(isbn)

    def active_for(self, member_id: str) -> list[Loan]:
        return [loan for loan in self.loans if loan.member_id == member_id and loan.returned is None]

    def active_loan(self, isbn: str, member_id: str) -> Loan | None:
        for loan in self.loans:
            if loan.isbn == isbn and loan.member_id == member_id and loan.returned is None:
                return loan
        return None

    def checkout(self, isbn: str, member_id: str, day: date) -> Loan:
        isbn = normalize_isbn(isbn)
        member = self.members.find(member_id)
        if not can_borrow(member, len(self.active_for(member.member_id))):
            raise LoanError(f"{member.name} is at the borrowing limit")
        if self.available(isbn) <= 0:
            raise LoanError(f"no copies of {self.books[isbn].title} available")
        loan = Loan(isbn=isbn, member_id=member.member_id, out=day, due=day + timedelta(days=loan_days(member)))
        self.loans.append(loan)
        return loan

    def return_book(self, isbn: str, member_id: str, day: date) -> Loan:
        loan = self.active_loan(normalize_isbn(isbn), member_id.strip().upper())
        loan.returned = day
        return loan

    def overdue(self, today: date) -> list[Loan]:
        return [loan for loan in self.loans if loan.returned is None and loan.days_late(today) > 0]

    def fines(self, today: date) -> dict[str, float]:
        totals: dict[str, float] = {}
        for loan in self.loans:
            amount = fine_for(loan, today)
            if amount:
                totals[loan.member_id] = totals.get(loan.member_id, 0.0) + amount
        return totals
