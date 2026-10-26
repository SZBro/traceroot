"""Statements and summaries."""
from .money import fmt

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def monthly_flow(txs, number: str) -> list[float]:
    months = [0.0] * 12
    for tx in txs:
        if tx.account == number:
            sign = 1 if tx.kind == "deposit" else -1
            months[tx.day.month - 1] += sign * tx.amount
        if tx.to_account == number:
            months[tx.day.month - 1] += tx.amount
    return months


def balances_table(bank) -> str:
    lines = [f"{'account':<10} {'owner':<12} {'kind':<9} {'balance':>12}"]
    for number, a in sorted(bank.accounts.items()):
        flag = " (below min)" if a.below_minimum() else ""
        lines.append(f"{number:<10} {a.owner:<12} {a.kind:<9} {fmt(a.balance):>12}{flag}")
    return "\n".join(lines)


def flow_line(txs, number: str) -> str:
    flow = monthly_flow(txs, number)
    cells = [f"{MONTHS[i]} {fmt(v)}" for i, v in enumerate(flow) if v]
    return f"{number}: " + ", ".join(cells)


def owner_summary(bank) -> str:
    rows = []
    for owner in bank.owners():
        total = sum(a.balance for a in bank.by_owner(owner))
        rows.append(f"  {owner:<12} {fmt(total):>12}")
    return "\n".join(rows)


def changes_block(changes: dict[str, float]) -> str:
    return "\n".join(f"  {n:<10} {fmt(v):>10}" for n, v in sorted(changes.items()))
