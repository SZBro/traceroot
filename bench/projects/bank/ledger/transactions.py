"""Transactions: parsing and applying them to a bank."""
import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .accounts import Bank
from .money import parse_amount, round_cents

FEES = {"withdraw": 0.0, "transfer": 0.0, "deposit": 0.0}

OVERDRAFT_LIMIT = -100.0


class OverdraftError(Exception):
    pass


@dataclass
class Transaction:
    day: date
    kind: str
    account: str
    amount: float
    to_account: str | None = None
    memo: str = ""


def parse_row(row: dict[str, str]) -> Transaction | None:
    if not row.get("day") or row["day"].startswith("#"):
        return None
    return Transaction(
        day=date.fromisoformat(row["day"]),
        kind=row["kind"].strip().lower(),
        account=row["account"].strip().upper(),
        amount=parse_amount(row["amount"]),
        to_account=(row.get("to_account") or "").strip().upper() or None,
        memo=(row.get("memo") or "").strip(),
    )


def load_transactions(path: Path) -> list[Transaction]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [tx for tx in (parse_row(r) for r in rows) if tx]


def _debit(bank: Bank, number: str, amount: float) -> None:
    account = bank.lookup(number)
    new_balance = round_cents(account.balance - amount)
    if new_balance < OVERDRAFT_LIMIT:
        raise OverdraftError(f"{number} would go to {new_balance}")
    account.balance = new_balance


def _credit(bank: Bank, number: str, amount: float) -> None:
    account = bank.lookup(number)
    account.balance = round_cents(account.balance + amount)


def apply(bank: Bank, tx: Transaction) -> None:
    fee = FEES[tx.kind]
    if tx.kind == "deposit":
        _credit(bank, tx.account, tx.amount)
    elif tx.kind == "withdraw":
        _debit(bank, tx.account, tx.amount + fee)
    elif tx.kind == "transfer":
        _debit(bank, tx.account, tx.amount + fee)
        _credit(bank, tx.to_account, tx.amount)
    else:
        raise ValueError(f"unknown transaction kind {tx.kind!r}")


def apply_all(bank: Bank, txs: list[Transaction]) -> int:
    for tx in sorted(txs, key=lambda t: t.day):
        apply(bank, tx)
    return len(txs)
