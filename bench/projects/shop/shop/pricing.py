TAX_RATES = {
    "WA": 0.101,
    "OR": 0.0,
    "CA": 0.0725,
}

SHIPPING_BRACKETS = [
    (1.0, 4.99),
    (3.0, 8.99),
    (10.0, 14.99),
]

FREE_SHIPPING_OVER = {"WA": 75.0, "OR": 75.0, "CA": 100.0}


def tax_rate(region: str) -> float:
    return TAX_RATES.get(region, 0.08)


def shipping_cost(weight_kg: float, region: str) -> float:
    for i in range(len(SHIPPING_BRACKETS)):
        limit, cost = SHIPPING_BRACKETS[i]
        if weight_kg <= limit:
            return cost
    return SHIPPING_BRACKETS[-1][1] + 2.5 * (weight_kg - SHIPPING_BRACKETS[-1][0])


def compute_total(subtotal: float, discount: float, shipping: float, region: str) -> float:
    discounted = subtotal * (1 - discount)
    if discounted >= FREE_SHIPPING_OVER.get(region, 100.0):
        shipping = 0.0
    taxed = discounted * (1 + tax_rate(region))
    return round(taxed + shipping, 2)


def format_money(amount: float) -> str:
    return f"${amount:,.2f}"
