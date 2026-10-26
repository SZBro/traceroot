import csv
from datetime import date
from pathlib import Path

from library import report
from library.catalog import build_index, load_books, search
from library.loans import LoanBook
from library.members import load_members

DATA = Path(__file__).resolve().parent / "data"
TODAY = date(2026, 10, 25)


def replay(ledger: LoanBook, path: Path) -> int:
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            day = date.fromisoformat(row["day"])
            if row["action"] == "checkout":
                ledger.checkout(row["isbn"], row["member_id"], day)
            elif row["action"] == "return":
                ledger.return_book(row["isbn"], row["member_id"], day)
            count += 1
    return count


def main() -> None:
    books = load_books(DATA / "books.csv")
    directory = load_members(DATA / "members.json")
    ledger = LoanBook(books, directory)
    n = replay(ledger, DATA / "events.csv")
    print(f"Replayed {n} events as of {TODAY}\n")
    print(report.availability(ledger))
    print("\nOverdue:\n" + report.overdue_block(ledger, TODAY))
    print("\nFines:\n" + report.fines_block(ledger, TODAY))
    print("\nMembers:\n" + report.members_block(directory, TODAY))
    index = build_index(books)
    print("\nSearch 'design patterns':\n" + report.search_block(search(index, books, "design patterns")))


if __name__ == "__main__":
    main()
