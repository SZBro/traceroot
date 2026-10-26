"""Benchmark cases: clean mini-projects + one known mutation per case.

Each mutation replaces one exact snippet (it must occur exactly once in the file). The mutated line is
the ground truth. This file lives outside the project folders, so it is never copied into a case and
the models never see it. `crash_ok=True` also accepts the crash line (e.g. a missing import, where
pointing at the use site is a fair answer). `kind` is our label, not shown to any model.
"""

PROJECTS = {
    "shop": {
        "cmd": "python main.py",
        "mutations": [
            {"id": "shop-01", "file": "shop/catalog.py", "kind": "wrong_type", "distance": "cross_file",
             "find": 'price=float(row["price"]),', "replace": 'price=row["price"],'},
            {"id": "shop-02", "file": "shop/catalog.py", "kind": "wrong_type", "distance": "cross_file",
             "find": 'stock=int(row["stock"]),', "replace": 'stock=row["stock"],'},
            {"id": "shop-03", "file": "shop/cart.py", "kind": "key_error", "distance": "same_file",
             "find": '"SAVE10": 0.10,', "replace": '"SAVE_10": 0.10,'},
            {"id": "shop-04", "file": "shop/catalog.py", "kind": "none_value", "distance": "cross_file",
             "find": "return catalog.get(sku.strip().upper())", "replace": "return catalog.get(sku.strip().lower())"},
            {"id": "shop-05", "file": "shop/pricing.py", "kind": "key_error", "distance": "crash_line",
             "find": "return TAX_RATES.get(region, 0.08)", "replace": "return TAX_RATES[region.lower()]"},
            {"id": "shop-06", "file": "main.py", "kind": "missing_import", "distance": "same_file",
             "find": "import json\n", "replace": "\n", "crash_ok": True},
            {"id": "shop-07", "file": "shop/pricing.py", "kind": "typo", "distance": "crash_line",
             "find": "taxed = discounted * (1 + tax_rate(region))",
             "replace": "taxed = discountd * (1 + tax_rate(region))"},
            {"id": "shop-08", "file": "shop/cart.py", "kind": "wrong_arguments", "distance": "crash_line",
             "find": "return pricing.shipping_cost(self.weight(), self.region)",
             "replace": "return pricing.shipping_cost(self.weight())"},
            {"id": "shop-09", "file": "shop/catalog.py", "kind": "none_value", "distance": "cross_file",
             "find": "catalog[product.sku] = product", "replace": "catalog[product.name] = product"},
        ],
    },
}
