import json
from pathlib import Path

from shop.cart import Cart
from shop.catalog import find_product, load_catalog, low_stock
from shop.pricing import format_money

DATA = Path(__file__).resolve().parent / "data"


def build_cart(order: dict, catalog) -> Cart:
    cart = Cart(region=order["region"], discount_code=order.get("discount"))
    for line in order["lines"]:
        product = find_product(catalog, line["sku"])
        cart.add(product, line["qty"])
    return cart


def receipt(order: dict, cart: Cart) -> str:
    rows = [f"Order {order['order_id']} ({cart.region})"]
    for line in cart.lines:
        rows.append(f"  {line.qty} x {line.product.name:<22} {format_money(line.amount):>10}")
    rows.append(f"  {'subtotal':<26} {format_money(cart.subtotal()):>10}")
    rows.append(f"  {'shipping':<26} {format_money(cart.shipping()):>10}")
    rows.append(f"  {'total':<26} {format_money(cart.total()):>10}")
    return "\n".join(rows)


def main() -> None:
    catalog = load_catalog(DATA / "catalog.csv")
    orders = json.loads((DATA / "orders.json").read_text(encoding="utf-8"))
    for order in orders:
        cart = build_cart(order, catalog)
        print(receipt(order, cart))
        print()
    low = low_stock(catalog)
    print("Low stock:", ", ".join(f"{p.sku} ({p.stock})" for p in low))


if __name__ == "__main__":
    main()
