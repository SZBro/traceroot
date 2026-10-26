def load_cart(user_id):
    carts = {1: ["book", "pen"], 2: []}
    items = carts.get(user_id)
    if not items:
        items = None
    return {"user": user_id, "items": items}


def price_items(items):
    prices = {"book": 12.5, "pen": 1.25}
    return [prices[i] for i in items]


def subtotal(cart):
    return sum(price_items(cart["items"]))


def checkout(user_id):
    cart = load_cart(user_id)
    return round(subtotal(cart) * 1.1, 2)


if __name__ == "__main__":
    print(checkout(1))
    print(checkout(2))
