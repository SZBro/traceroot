"""Interest and monthly fees."""
from datetime import date

from .accounts import ACCOUNT_KINDS, Account, Bank
from .money import round_cents

DAYS_IN_YEAR = 365


def days_open(account: Account, today: date) -> int:
    return (today - account.opened).days


def monthly_interest(account: Account, days: int) -> float:
    rate = ACCOUNT_KINDS[account.kind]["rate"]
    if account.balance <= 0:
        return 0.0
    return round_cents(account.balance * rate * days / DAYS_IN_YEAR)


def monthly_fee(account: Account) -> float:
    fee = account.settings["monthly_fee"]
    return 0.0 if account.balance >= 1500 else fee


def month_end(bank: Bank, days: int) -> dict[str, float]:
    changes = {}
    for number, account in bank.accounts.items():
        delta = monthly_interest(account, days) - monthly_fee(account)
        account.balance = round_cents(account.balance + delta)
        changes[number] = delta
    return changes


def loyalty_years(bank: Bank, today: date) -> dict[str, float]:
    return {n: round(days_open(a, today) / DAYS_IN_YEAR, 1) for n, a in bank.accounts.items()}
