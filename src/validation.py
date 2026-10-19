"""Row-level cleaning and database data-quality checks.

Cleaning never silently fixes money values: invalid rows are rejected with a reason
so they can be reviewed (see data/rejected_rows.csv). The only repair is that a blank
delivery area is kept and reported as 'Unknown'.
"""
from __future__ import annotations

import pandas as pd

VALID_STATUSES = {"Delivered", "Cancelled"}


def clean_orders(df: pd.DataFrame, customer_ids: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    reasons = pd.Series("", index=df.index, dtype=object)

    def flag(mask, text):
        nonlocal reasons
        mask = mask & (reasons == "")
        reasons = reasons.mask(mask, text)

    flag(df["order_id"].isna(), "missing order_id")
    flag(df.duplicated("order_id", keep="first") & df["order_id"].notna(), "duplicate order_id")
    parsed = pd.to_datetime(df["order_datetime"], errors="coerce")
    flag(parsed.isna(), "invalid order_datetime")
    flag(~df["order_status"].isin(VALID_STATUSES), "invalid order_status")
    flag(~df["customer_id"].isin(customer_ids), "unknown customer_id")

    rejected = df[reasons != ""].assign(reject_reason=reasons[reasons != ""])
    clean = df[reasons == ""].copy()
    clean["order_id"] = clean["order_id"].astype(int)
    clean["delivery_area"] = clean["delivery_area"].where(
        clean["delivery_area"].fillna("").str.strip() != "", None
    )
    return clean, rejected


def clean_order_items(
    df: pd.DataFrame, order_ids: set[int], product_ids: set[int]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    for col in ("discount_amount", "refund_amount", "returned_quantity"):
        df[col] = df[col].fillna(0)  # missing optional adjustment == none
    reasons = pd.Series("", index=df.index, dtype=object)

    def flag(mask, text):
        nonlocal reasons
        mask = mask.fillna(False) & (reasons == "")
        reasons = reasons.mask(mask, text)

    flag(df["order_item_id"].isna(), "missing order_item_id")
    flag(df.duplicated("order_item_id", keep="first") & df["order_item_id"].notna(),
         "duplicate order_item_id")
    flag(~df["order_id"].isin(order_ids), "unknown order_id")
    flag(~df["product_id"].isin(product_ids), "unknown product_id")
    q = pd.to_numeric(df["quantity"], errors="coerce")
    flag(q.isna() | (q <= 0) | (q % 1 != 0), "invalid quantity")
    p = pd.to_numeric(df["unit_selling_price"], errors="coerce")
    flag(p.isna() | (p < 0), "invalid unit_selling_price")
    c = pd.to_numeric(df["unit_product_cost"], errors="coerce")
    flag(c.isna() | (c < 0), "invalid unit_product_cost")
    flag((df["discount_amount"] < 0) | (df["refund_amount"] < 0), "negative discount/refund")
    flag(df["returned_quantity"] > q, "returned_quantity exceeds quantity")
    flag(df["discount_amount"] + df["refund_amount"] > q * p + 1e-6,
         "discount + refund exceeds gross sales")

    rejected = df[reasons != ""].assign(reject_reason=reasons[reasons != ""])
    clean = df[reasons == ""].copy()
    for col in ("order_item_id", "order_id", "product_id", "quantity", "returned_quantity"):
        clean[col] = clean[col].astype(int)
    return clean, rejected


def check_database(conn) -> pd.DataFrame:
    """Data-quality summary shown in the dashboard. severity: ok / warning / error."""
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    checks = [
        ("Order items", q("SELECT COUNT(*) FROM order_items"), "info"),
        ("Orders", q("SELECT COUNT(*) FROM orders"), "info"),
        ("Cancelled orders (excluded from sales)",
         q("SELECT COUNT(*) FROM orders WHERE order_status='Cancelled'"), "info"),
        ("Orders with missing delivery area (shown as 'Unknown')",
         q("SELECT COUNT(*) FROM orders WHERE delivery_area IS NULL OR TRIM(delivery_area)=''"),
         "warning"),
        ("Order items with refund or return",
         q("SELECT COUNT(*) FROM order_items WHERE refund_amount>0 OR returned_quantity>0"), "info"),
        ("Orders without any items",
         q("SELECT COUNT(*) FROM orders o WHERE NOT EXISTS "
           "(SELECT 1 FROM order_items i WHERE i.order_id=o.order_id)"), "warning"),
        ("Items with negative net sales",
         q("SELECT COUNT(*) FROM v_item_facts WHERE net_sales < 0"), "error"),
        ("Orphan order items (no order)",
         q("SELECT COUNT(*) FROM order_items i LEFT JOIN orders o USING(order_id) "
           "WHERE o.order_id IS NULL"), "error"),
    ]
    out = pd.DataFrame(checks, columns=["Check", "Count", "kind"])
    out["Status"] = out.apply(
        lambda r: "ℹ️" if r.kind == "info" else ("✅" if r.Count == 0 else
                                                  ("⚠️" if r.kind == "warning" else "❌")), axis=1)
    return out[["Status", "Check", "Count"]]
