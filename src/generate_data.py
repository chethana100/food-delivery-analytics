"""Reproducible synthetic data generator.

    python -m src.generate_data            # uses the fixed seed in config.py

Produces data/*.csv and data/food_delivery.db. A handful of deliberately dirty rows
are injected into the raw data so the validation layer has something to reject;
rejected rows are written to data/rejected_rows.csv.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import config, db
from .validation import clean_order_items, clean_orders

AREAS = {"Indiranagar": 1.5, "Koramangala": 1.4, "Whitefield": 1.0, "HSR Layout": 1.1,
         "Jayanagar": 0.8, "Electronic City": 0.6}

# (name, brand, type, base_price ₹, cost_ratio, popularity)
# cost_ratio > 1 => sold below cost (deliberate loss-makers for FR-07).
CATALOGUE = [
    # Beverages
    ("Masala Chai", "Chai Point Co", "Beverages", 60, .35, 3.0),
    ("Cold Coffee", "Brew Bros", "Beverages", 140, .38, 2.4),
    ("Fresh Lime Soda", "Chai Point Co", "Beverages", 80, .30, 2.0),
    ("Mango Lassi", "Dairy Delight", "Beverages", 110, .42, 1.8),
    ("Cola 500ml", "Fizz & Co", "Beverages", 55, .55, 3.2),
    ("Iced Tea Peach", "Brew Bros", "Beverages", 120, .40, 1.2),
    ("Sparkling Water", "Fizz & Co", "Beverages", 70, 1.10, 0.9),   # loss-maker
    ("Cold-Pressed Juice", "Green Bowl", "Beverages", 190, .60, 0.7),
    # Burgers
    ("Classic Veg Burger", "Burger Barn", "Burgers", 149, .45, 3.0),
    ("Chicken Zinger Burger", "Burger Barn", "Burgers", 199, .50, 2.6),
    ("Double Patty Burger", "Burger Barn", "Burgers", 279, .55, 1.4),
    ("Paneer Tikka Burger", "Spice Route", "Burgers", 179, .48, 1.6),
    ("Mini Burger Trio", "Burger Barn", "Burgers", 239, 1.12, 0.8),  # loss-maker
    # Pizza
    ("Margherita Pizza", "Pizza Primo", "Pizza", 259, .40, 2.4),
    ("Farmhouse Pizza", "Pizza Primo", "Pizza", 349, .46, 1.8),
    ("Pepperoni Pizza", "Pizza Primo", "Pizza", 399, .52, 1.5),
    ("Cheese Burst Pizza", "Pizza Primo", "Pizza", 429, 1.08, 0.9),  # loss-maker
    ("Family Feast Pizza Box", "Pizza Primo", "Pizza", 1099, .55, 0.25),  # high revenue/low units
    # Biryani & Mains
    ("Chicken Dum Biryani", "Spice Route", "Biryani & Mains", 289, .50, 3.4),
    ("Veg Biryani", "Spice Route", "Biryani & Mains", 219, .44, 1.7),
    ("Butter Chicken Combo", "Spice Route", "Biryani & Mains", 329, .52, 2.0),
    ("Dal Makhani Bowl", "Green Bowl", "Biryani & Mains", 189, .40, 1.4),
    ("Party Biryani Handi", "Spice Route", "Biryani & Mains", 1299, .58, 0.22),  # high revenue/low units
    # Sides
    ("French Fries", "Burger Barn", "Sides", 99, .28, 3.6),
    ("Garlic Bread", "Pizza Primo", "Sides", 119, .35, 2.2),
    ("Chicken Wings (6)", "Burger Barn", "Sides", 189, .56, 1.5),
    ("Onion Rings", "Burger Barn", "Sides", 109, 1.06, 1.0),         # loss-maker
    ("Paneer Tikka Starter", "Spice Route", "Sides", 229, .47, 1.1),
    # Desserts
    ("Chocolate Brownie", "Sweet Tooth", "Desserts", 129, .38, 2.0),
    ("Gulab Jamun (2)", "Sweet Tooth", "Desserts", 89, .33, 1.9),
    ("Ice Cream Tub", "Dairy Delight", "Desserts", 249, .50, 1.0),
    ("Red Velvet Cake Slice", "Sweet Tooth", "Desserts", 159, 1.15, 0.8),  # loss-maker
    ("Rasmalai (3)", "Sweet Tooth", "Desserts", 169, .45, 1.2),
    # Healthy
    ("Grilled Chicken Salad", "Green Bowl", "Healthy", 249, .50, 1.1),
    ("Quinoa Power Bowl", "Green Bowl", "Healthy", 279, .54, 0.9),
    ("Avocado Toast", "Green Bowl", "Healthy", 219, .58, 0.8),
    ("Protein Smoothie Bowl", "Green Bowl", "Healthy", 259, 1.07, 0.6),  # loss-maker
    ("Hummus Wrap", "Green Bowl", "Healthy", 199, .46, 0.9),
]

FIRST = ["Aarav", "Vivaan", "Aditya", "Ishaan", "Rohan", "Karan", "Neha", "Priya", "Ananya", "Diya",
         "Meera", "Kavya", "Rahul", "Sneha", "Arjun", "Pooja", "Nikhil", "Divya", "Siddharth", "Riya"]
LAST = ["Sharma", "Iyer", "Reddy", "Nair", "Gupta", "Patel", "Menon", "Rao", "Das", "Kulkarni",
        "Bose", "Shetty", "Joshi", "Kapoor", "Hegde"]


def build_dataframes(seed: int = config.SEED, start: str = config.DATA_START,
                     end: str = config.DATA_END):
    rng = np.random.default_rng(seed)

    products = pd.DataFrame(
        [(i + 1, n, b, t) for i, (n, b, t, *_rest) in enumerate(CATALOGUE)],
        columns=["product_id", "product_name", "brand", "product_type"])
    base_price = np.array([c[3] for c in CATALOGUE], dtype=float)
    cost_ratio = np.array([c[4] for c in CATALOGUE])
    pop = np.array([c[5] for c in CATALOGUE])
    pop_p = pop / pop.sum()

    n_cust = 140
    customers = pd.DataFrame({
        "customer_id": [f"C{i:04d}" for i in range(1, n_cust + 1)],
        "customer_name": [f"{FIRST[rng.integers(len(FIRST))]} {LAST[rng.integers(len(LAST))]}"
                          for _ in range(n_cust)]})
    cust_w = rng.pareto(1.6, n_cust) + 0.3          # a few heavy buyers
    cust_p = cust_w / cust_w.sum()
    area_names = list(AREAS)
    area_p = np.array(list(AREAS.values())) / sum(AREAS.values())
    home_area = rng.choice(len(area_names), n_cust, p=area_p)

    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    days = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
    hour_p = np.array([0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 5, 10, 12, 9, 5, 4, 4, 5, 8, 13, 14, 10, 5, 1], float)
    hour_p /= hour_p.sum()

    orders, items = [], []
    oid = iid = 0
    for k, day in enumerate(days):
        growth = 1 + 0.6 * k / len(days)                 # business grows ~60% over the span
        weekend = 1.35 if day.weekday() >= 4 else 1.0    # Fri-Sun peak
        n_orders = rng.poisson(16 * growth * weekend)
        for _ in range(n_orders):
            oid += 1
            c = int(rng.choice(n_cust, p=cust_p))
            area = area_names[home_area[c]] if rng.random() < 0.85 else \
                area_names[int(rng.choice(len(area_names), p=area_p))]
            ts = f"{day:%Y-%m-%d} {int(rng.choice(24, p=hour_p)):02d}:{rng.integers(60):02d}:{rng.integers(60):02d}"
            status = "Cancelled" if rng.random() < 0.04 else "Delivered"
            orders.append((oid, ts, customers.customer_id[c], area, status))
            n_lines = int(rng.choice([1, 2, 3, 4], p=[.35, .37, .20, .08]))
            for p_idx in rng.choice(len(CATALOGUE), n_lines, replace=False, p=pop_p):
                iid += 1
                qty = int(rng.choice([1, 2, 3, 4], p=[.62, .25, .09, .04]))
                hike = 1.05 if day >= date(2026, 4, 1) else 1.0
                price = round(base_price[p_idx] * hike * (1 + rng.normal(0, .01))) 
                cost = round(base_price[p_idx] * cost_ratio[p_idx] * (1 + rng.normal(0, .03)) *
                             (1 + 0.04 * k / len(days)), 2)
                gross = qty * price
                disc = 0.0
                loss_item = cost_ratio[p_idx] > 1
                if rng.random() < (0.55 if loss_item else 0.28):
                    disc = round(gross * rng.uniform(.05, .25 if not loss_item else .30), 2)
                refund, ret_q = 0.0, 0
                if status == "Delivered":
                    r = rng.random()
                    net_line = gross - disc
                    if r < .012:                              # full return
                        ret_q, refund = qty, round(net_line, 2)
                    elif r < .020 and qty >= 2:               # partial return
                        ret_q, refund = 1, round(net_line / qty, 2)
                    elif r < .030:                            # refund w/o return (compensation)
                        refund = round(net_line * rng.uniform(.2, .5), 2)
                items.append((iid, oid, p_idx + 1, qty, float(price), disc, refund, ret_q, cost))

    orders = pd.DataFrame(orders, columns=["order_id", "order_datetime", "customer_id",
                                           "delivery_area", "order_status"])
    items = pd.DataFrame(items, columns=["order_item_id", "order_id", "product_id", "quantity",
                                         "unit_selling_price", "discount_amount", "refund_amount",
                                         "returned_quantity", "unit_product_cost"])
    return customers, products, orders, items


def inject_dirty_rows(orders: pd.DataFrame, items: pd.DataFrame, seed: int = config.SEED):
    """Add a few bad rows to demonstrate validation. Returns new frames."""
    rng = np.random.default_rng(seed + 1)
    orders, items = orders.copy(), items.copy()
    # blank delivery areas (kept; reported as 'Unknown')
    blank = rng.choice(orders.index, 25, replace=False)
    orders.loc[blank, "delivery_area"] = None
    # duplicates, invalid quantities / prices, orphan rows
    dup = items.sample(6, random_state=seed)
    bad_q = items.sample(4, random_state=seed + 2).assign(order_item_id=lambda d: d.order_item_id + 900000,
                                                         quantity=[0, -2, 0, -1])
    bad_p = items.sample(3, random_state=seed + 3).assign(order_item_id=lambda d: d.order_item_id + 910000,
                                                         unit_selling_price=[-50.0, np.nan, -1.0])
    orphan = items.sample(2, random_state=seed + 4).assign(order_item_id=lambda d: d.order_item_id + 920000,
                                                          order_id=[99999991, 99999992])
    items = pd.concat([items, dup, bad_q, bad_p, orphan], ignore_index=True)
    return orders, items


def build_database(db_path=config.DB_PATH, seed=config.SEED, start=config.DATA_START,
                   end=config.DATA_END, write_csv=True, inject_dirty=True):
    customers, products, orders, items = build_dataframes(seed, start, end)
    if inject_dirty:
        orders, items = inject_dirty_rows(orders, items, seed)

    clean_o, rej_o = clean_orders(orders, set(customers.customer_id))
    clean_i, rej_i = clean_order_items(items, set(clean_o.order_id), set(products.product_id))

    db_path = db.Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = db.connect(db_path)
    db.create_schema(conn)
    customers.to_sql("customers", conn, if_exists="append", index=False)
    products.to_sql("products", conn, if_exists="append", index=False)
    clean_o.to_sql("orders", conn, if_exists="append", index=False)
    clean_i[items.columns].to_sql("order_items", conn, if_exists="append", index=False)
    conn.commit()

    if write_csv:
        out = db_path.parent
        customers.to_csv(out / "customers.csv", index=False)
        products.to_csv(out / "products.csv", index=False)
        clean_o.to_csv(out / "orders.csv", index=False)
        clean_i.to_csv(out / "order_items.csv", index=False)
        pd.concat([rej_o.assign(table="orders"), rej_i.assign(table="order_items")],
                  ignore_index=True).to_csv(out / "rejected_rows.csv", index=False)
    return conn, {"orders": len(clean_o), "order_items": len(clean_i),
                  "rejected_orders": len(rej_o), "rejected_items": len(rej_i)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=config.SEED)
    ap.add_argument("--start", default=config.DATA_START)
    ap.add_argument("--end", default=config.DATA_END)
    ap.add_argument("--db", default=str(config.DB_PATH))
    a = ap.parse_args()
    _, stats = build_database(a.db, a.seed, a.start, a.end)
    print("Database written to", a.db, stats)
