from datetime import date
from pathlib import Path

from ledger import interest, statement
from ledger.accounts import load_bank
from ledger.money import fmt
from ledger.transactions import apply_all, load_transactions

DATA = Path(__file__).resolve().parent / "data"
TODAY = date(2026, 12, 31)


def main() -> None:
    bank = load_bank(DATA / "accounts.json")
    txs = load_transactions(DATA / "transactions.csv")
    n = apply_all(bank, txs)
    print(f"Applied {n} transactions; deposits held: {fmt(bank.total_deposits())}\n")
    print(statement.balances_table(bank))
    print("\nMonthly flow:")
    for number in sorted(bank.accounts):
        print("  " + statement.flow_line(txs, number))
    changes = interest.month_end(bank, days=31)
    print("\nMonth-end interest and fees:\n" + statement.changes_block(changes))
    print("\nBy owner:\n" + statement.owner_summary(bank))
    years = interest.loyalty_years(bank, TODAY)
    print("\nYears open: " + ", ".join(f"{k} {v}" for k, v in sorted(years.items())))


if __name__ == "__main__":
    main()
