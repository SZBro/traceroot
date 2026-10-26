ORDER_TEXT = """apple,3,0.50
bread,1,2.25
milk,2,1.10"""


def parse_order(text):
    rows = []
    for line in text.splitlines():
        name, qty, price = line.split(",")
        rows.append({"name": name, "qty": qty, "price": float(price)})
    return rows


def line_total(row):
    return row["price"] * row["qty"]


def order_total(rows):
    return sum(line_total(r) for r in rows)


if __name__ == "__main__":
    print(order_total(parse_order(ORDER_TEXT)))
