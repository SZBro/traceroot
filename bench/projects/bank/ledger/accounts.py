"""Accounts and the bank that holds them."""
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .money import parse_amount

ACCOUNT_KINDS = {
    "checking": {"rate": 0.0005, "min_balance": 0.0, "monthly_fee": 4.00},
    "savings": {"rate": 0.0400, "min_balance": 100.0, "monthly_fee": 0.0},
    "cd": {"rate": 0.0475, "min_balance": 1000.0, "monthly_fee": 0.0},
}


class UnknownAccount(KeyError):
    pass


@dataclass
class Account:
    number: str
    owner: str
    kind: str
    balance: float
    opened: date

    @property
    def settings(self) -> dict:
        return ACCOUNT_KINDS[self.kind]

    def below_minimum(self) -> bool:
        return self.balance < self.settings["min_balance"]


class Bank:
    def __init__(self) -> None:
        self.accounts: dict[str, Account] = {}

    def open_account(self, account: Account) -> Account:
        if account.number in self.accounts:
            raise ValueError(f"duplicate account {account.number}")
        self.accounts[account.number] = account
        return account

    def lookup(self, number: str) -> Account | None:
        return self.accounts.get(number.strip().upper())

    def by_owner(self, owner: str) -> list[Account]:
        return [a for a in self.accounts.values() if a.owner == owner]

    def owners(self) -> list[str]:
        return sorted({a.owner for a in self.accounts.values()})

    def total_deposits(self) -> float:
        return sum(a.balance for a in self.accounts.values())


def load_bank(path: Path) -> Bank:
    bank = Bank()
    for raw in json.loads(path.read_text(encoding="utf-8")):
        bank.open_account(Account(
            number=raw["number"].strip().upper(),
            owner=raw["owner"].strip(),
            kind=raw["kind"].strip().lower(),
            balance=parse_amount(raw["balance"]),
            opened=date.fromisoformat(raw["opened"]),
        ))
    return bank
