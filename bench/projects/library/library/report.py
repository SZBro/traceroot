"""Text reports."""
from datetime import date

TITLE_WIDTH = 30


def money(x: float) -> str:
    return f"${x:,.2f}"


def availability(ledger) -> str:
    lines = [f"{'title':<{TITLE_WIDTH}} {'avail':>5} / copies"]
    for isbn, book in sorted(ledger.books.items(), key=lambda kv: kv[1].title):
        lines.append(f"{book.title[:TITLE_WIDTH]:<{TITLE_WIDTH}} {ledger.available(isbn):>5} / {book.copies}")
    return "\n".join(lines)


def overdue_block(ledger, today: date) -> str:
    rows = []
    for loan in ledger.overdue(today):
        book = ledger.books[loan.isbn]
        member = ledger.members.find(loan.member_id)
        rows.append(f"  {member.name:<14} {book.title[:TITLE_WIDTH]:<{TITLE_WIDTH}} {loan.days_late(today)}d late")
    return "\n".join(rows) or "  (none)"


def fines_block(ledger, today: date) -> str:
    fines = ledger.fines(today)
    rows = [f"  {ledger.members.find(mid).name:<14} {money(amount):>8}" for mid, amount in sorted(fines.items())]
    return "\n".join(rows) or "  (none)"


def members_block(directory, today: date) -> str:
    return "\n".join(f"  {m.name:<14} {m.tier:<8} {m.years(today):>4} yrs" for m in directory.all())


def search_block(results) -> str:
    return "\n".join(f"  {b.short()}" for b in results[:3]) or "  (no matches)"
