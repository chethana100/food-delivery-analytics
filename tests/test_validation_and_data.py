import pandas as pd

from src import analytics as an
from src import db
from src.generate_data import build_database, build_dataframes
from src.validation import check_database, clean_order_items, clean_orders


def _items(**over):
    base = dict(order_item_id=1, order_id=1, product_id=1, quantity=2, unit_selling_price=100.0,
                discount_amount=0.0, refund_amount=0.0, returned_quantity=0, unit_product_cost=40.0)
    base.update(over)
    return base


def test_clean_items_rejects_bad_rows_with_reasons():
    df = pd.DataFrame([
        _items(order_item_id=1),
        _items(order_item_id=1),                                  # duplicate
        _items(order_item_id=2, quantity=0),
        _items(order_item_id=3, quantity=-1),
        _items(order_item_id=4, unit_selling_price=float("nan")),
        _items(order_item_id=5, unit_selling_price=-5.0),
        _items(order_item_id=6, order_id=999),                    # orphan
        _items(order_item_id=7, returned_quantity=5),             # > quantity
        _items(order_item_id=8, discount_amount=500.0),           # > gross
        _items(order_item_id=9, discount_amount=float("nan")),    # missing optional -> 0, kept
    ])
    clean, rej = clean_order_items(df, {1}, {1})
    assert sorted(clean.order_item_id) == [1, 9]
    assert len(rej) == 8
    assert set(rej.reject_reason) >= {"duplicate order_item_id", "invalid quantity",
                                      "invalid unit_selling_price", "unknown order_id",
                                      "returned_quantity exceeds quantity"}
    assert clean.set_index("order_item_id").loc[9, "discount_amount"] == 0


def test_clean_orders_rules():
    df = pd.DataFrame({
        "order_id": [1, 1, 2, 3, 4],
        "order_datetime": ["2026-01-01 10:00:00", "2026-01-01 10:00:00", "not a date",
                           "2026-01-02 10:00:00", "2026-01-03 10:00:00"],
        "customer_id": ["C1", "C1", "C1", "C1", "C9"],
        "delivery_area": ["N", "N", "N", "  ", "N"],
        "order_status": ["Delivered", "Delivered", "Delivered", "Cancelled", "Delivered"]})
    clean, rej = clean_orders(df, {"C1"})
    assert list(clean.order_id) == [1, 3]
    assert clean.delivery_area.isna().tolist() == [False, True]   # blank area -> NULL -> 'Unknown'
    assert len(rej) == 3


def test_generator_is_reproducible_and_meets_dataset_requirements():
    c1, p1, o1, i1 = build_dataframes(seed=7, start="2025-01-01", end="2025-12-31")
    c2, p2, o2, i2 = build_dataframes(seed=7, start="2025-01-01", end="2025-12-31")
    pd.testing.assert_frame_equal(i1, i2)
    pd.testing.assert_frame_equal(o1, o2)
    assert len(i1) >= 5000 and len(c1) >= 100 and len(p1) >= 30
    assert p1.brand.nunique() >= 5 and p1.product_type.nunique() >= 5
    assert (p1.product_type == "Beverages").sum() >= 3
    assert o1.delivery_area.nunique() >= 5
    assert (o1.order_status == "Cancelled").any() and (i1.refund_amount > 0).any()


def test_built_database_passes_checks_and_has_five_loss_makers(tmp_path):
    conn, stats = build_database(tmp_path / "t.db", write_csv=True)
    assert stats["rejected_items"] == 15                           # injected dirty rows caught
    assert (tmp_path / "rejected_rows.csv").exists()
    dq = check_database(conn)
    assert dq.loc[dq.Check.str.startswith("Orphan"), "Count"].item() == 0
    assert dq.loc[dq.Check.str.startswith("Items with negative"), "Count"].item() == 0
    from datetime import date
    assert len(an.loss_making(conn, date(2026, 1, 1), date(2026, 12, 31), 5)) == 5
    # product attributes are stable: one row per product, no brand/category drift possible
    n = conn.execute("SELECT COUNT(*) FROM (SELECT product_id FROM v_item_facts "
                     "GROUP BY product_id HAVING COUNT(DISTINCT brand||product_type) > 1)").fetchone()[0]
    assert n == 0


def test_schema_constraints_block_bad_inserts(b):
    import sqlite3
    import pytest
    b.product(1, "A")
    b.order("2026-01-01", [dict(product=1, qty=1, price=10, cost=1)])
    with pytest.raises(sqlite3.IntegrityError):
        b.conn.execute("INSERT INTO order_items VALUES (99,1,1,0,10,0,0,0,1)")   # qty 0
    with pytest.raises(sqlite3.IntegrityError):
        b.conn.execute("INSERT INTO order_items VALUES (98,1,77,1,10,0,0,0,1)")  # FK product
