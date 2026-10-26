"""Money parsing and formatting."""
import re

AMOUNT_RE = re.compile(r"^\(?-?\$?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\)?$")


def parse_amount(text: str) -> float:
    s = text.strip()
    m = AMOUNT_RE.match(s)
    if not m:
        raise ValueError(f"bad amount {text!r}")
    cleaned = m.group(1).replace(",", "")
    negative = s.startswith("(") or s.startswith("-")
    value = float(cleaned)
    return -value if negative else value


def fmt(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def round_cents(amount: float) -> float:
    return round(amount + 1e-9, 2)
