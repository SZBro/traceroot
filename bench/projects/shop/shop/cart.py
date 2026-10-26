from dataclasses import dataclass, field

from . import pricing
from .catalog import Product

DISCOUNTS = {
    "SAVE10": 0.10,
    "WELCOME5": 0.05,
    "VIP20": 0.20,
}


class OutOfStock(Exception):
    pass


@dataclass
class Line:
    product: Product
    qty: int

    @property
    def amount(self) -> float:
        return self.product.price * self.qty


@dataclass
class Cart:
    region: str
    lines: list[Line] = field(default_factory=list)
    discount_code: str | None = None

    def add(self, product: Product, qty: int) -> None:
        if qty > product.stock:
            raise OutOfStock(f"only {product.stock} of {product.sku} left")
        for line in self.lines:
            if line.product.sku == product.sku:
                line.qty += qty
                return
        self.lines.append(Line(product, qty))

    def subtotal(self) -> float:
        return sum(line.amount for line in self.lines)

    def weight(self) -> float:
        return sum(line.product.weight_kg * line.qty for line in self.lines)

    def discount_rate(self) -> float:
        if not self.discount_code:
            return 0.0
        return DISCOUNTS[self.discount_code]

    def shipping(self) -> float:
        return pricing.shipping_cost(self.weight(), self.region)

    def total(self) -> float:
        return pricing.compute_total(self.subtotal(), self.discount_rate(), self.shipping(), self.region)
