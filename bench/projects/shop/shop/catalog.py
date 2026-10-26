import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Product:
    sku: str
    name: str
    price: float
    stock: int
    weight_kg: float


def load_catalog(path: Path) -> dict[str, Product]:
    catalog = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            product = Product(
                sku=row["sku"].strip(),
                name=row["name"].strip(),
                price=float(row["price"]),
                stock=int(row["stock"]),
                weight_kg=float(row["weight_kg"]),
            )
            catalog[product.sku] = product
    return catalog


def find_product(catalog: dict[str, Product], sku: str) -> Product | None:
    return catalog.get(sku.strip().upper())


def low_stock(catalog: dict[str, Product], limit: int = 5) -> list[Product]:
    return sorted((p for p in catalog.values() if p.stock <= limit), key=lambda p: p.stock)
