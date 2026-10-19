"""Analytics layer: every business question is a SQL aggregation over v_item_facts.

Division of labour
  SQL    : filtering by date, joins, SUM/COUNT aggregation, deterministic ordering.
  Python : profit margin (needs zero/negative-sales guard), rank numbers, zero-filling
           missing months for trend charts, formatting.

All date arguments are inclusive `datetime.date` bounds on the order date (IST).

Ranking tie-breaks (deterministic, applied in SQL ORDER BY):
  by net sales  -> net sales DESC, units DESC, name ASC
  by units sold -> units DESC, net sales DESC, name ASC
  by profit     -> profit DESC (or ASC for losses), net sales DESC, name ASC
`rank` is simply the row position under that ordering, so tied rows get consecutive ranks.
"""
from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd

GRAINS = {
    "Daily": "order_date",
    "Weekly": "week_start",                                # Monday-start
    "Monthly": "strftime('%Y-%m-01', order_date)",
    "Yearly": "strftime('%Y-01-01', order_date)",
}
_ENTITY_COLS = {"product": ("product_id", "product_name"),
                "customer": ("f.customer_id", "COALESCE(c.customer_name, '') || ' (' || f.customer_id || ')'")}


def _params(start: date, end: date) -> tuple[str, str]:
    return start.isoformat(), end.isoformat()


def _query(conn, sql: str, params=()) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def margin_pct(profit, net_sales):
    """Profit / net sales * 100. None (shown as N/A) when net sales <= 0."""
    if net_sales is None or pd.isna(net_sales) or net_sales <= 0:
        return None
    return round(profit / net_sales * 100, 2)


def _add_rank(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True)
    df.insert(0, "rank", range(1, len(df) + 1))
    return df


def _add_profit_cols(df: pd.DataFrame) -> pd.DataFrame:
    df["profit"] = (df["net_sales"] - df["product_cost"]).round(2)
    df["margin_pct"] = [margin_pct(p, n) for p, n in zip(df["profit"], df["net_sales"])]
    return df


# --------------------------------------------------------------------------- summary
def summary(conn, start: date, end: date) -> dict:
    row = conn.execute(
        """SELECT COALESCE(SUM(net_sales),0), COUNT(DISTINCT order_id),
                  COALESCE(SUM(units_sold),0), COALESCE(SUM(net_sales - product_cost),0)
           FROM v_item_facts WHERE order_date BETWEEN ? AND ?""", _params(start, end)).fetchone()
    return {"net_sales": round(row[0], 2), "orders": row[1], "units": int(row[2]),
            "profit": round(row[3], 2)}


# --------------------------------------------------------------------------- FR-01
def top_brands(conn, start: date, end: date, limit: int | None = None) -> pd.DataFrame:
    df = _query(conn, """
        SELECT brand, ROUND(SUM(net_sales),2) AS net_sales, SUM(units_sold) AS units_sold
        FROM v_item_facts WHERE order_date BETWEEN ? AND ?
        GROUP BY brand ORDER BY net_sales DESC, units_sold DESC, brand ASC""", _params(start, end))
    return _add_rank(df.head(limit) if limit else df)


# --------------------------------------------------------------------------- FR-02
def best_selling_products(conn, start: date, end: date, limit: int | None = 10) -> pd.DataFrame:
    df = _query(conn, """
        SELECT product_name, brand, product_type, SUM(units_sold) AS units_sold,
               ROUND(SUM(net_sales),2) AS net_sales
        FROM v_item_facts WHERE order_date BETWEEN ? AND ?
        GROUP BY product_id ORDER BY units_sold DESC, net_sales DESC, product_name ASC""",
                 _params(start, end))
    return _add_rank(df.head(limit) if limit else df)


# --------------------------------------------------------------------------- FR-03 / FR-04
def top_entities(conn, entity: str, year: int, n: int = 5) -> pd.DataFrame:
    """Top-n products or customers by NET SALES for a calendar year."""
    key, label = _ENTITY_COLS[entity]
    join = "LEFT JOIN customers c ON c.customer_id = f.customer_id" if entity == "customer" else ""
    f = "f." if entity == "customer" else ""
    df = _query(conn, f"""
        SELECT {key} AS entity_id, {label} AS entity_name, ROUND(SUM({f}net_sales),2) AS net_sales,
               SUM({f}units_sold) AS units_sold
        FROM v_item_facts f {join}
        WHERE order_date BETWEEN ? AND ?
        GROUP BY {key} ORDER BY net_sales DESC, units_sold DESC, entity_name ASC LIMIT ?""",
                 (f"{year}-01-01", f"{year}-12-31", n))
    return _add_rank(df)


def monthly_trend(conn, entity: str, year: int, ids: list, through_month: int = 12) -> pd.DataFrame:
    """Long frame (month, entity_name, net_sales) with zero-filled months 1..through_month."""
    if not ids:
        return pd.DataFrame(columns=["month", "entity_name", "net_sales"])
    key, label = _ENTITY_COLS[entity]
    join = "LEFT JOIN customers c ON c.customer_id = f.customer_id" if entity == "customer" else ""
    f = "f." if entity == "customer" else ""
    marks = ",".join("?" * len(ids))
    raw = _query(conn, f"""
        SELECT CAST(strftime('%m', order_date) AS INTEGER) AS m, {key} AS entity_id,
               {label} AS entity_name, SUM({f}net_sales) AS net_sales
        FROM v_item_facts f {join}
        WHERE order_date BETWEEN ? AND ? AND {key} IN ({marks})
        GROUP BY m, {key}""", (f"{year}-01-01", f"{year}-12-31", *ids))
    names = raw.drop_duplicates("entity_id").set_index("entity_id")["entity_name"].to_dict()
    # zero-fill: every (entity, month) pair gets a row so lines don't skip months
    grid = pd.MultiIndex.from_product([ids, range(1, through_month + 1)], names=["entity_id", "m"])
    out = (raw.set_index(["entity_id", "m"])["net_sales"].reindex(grid, fill_value=0.0)
           .reset_index())
    out["entity_name"] = out["entity_id"].map(names)
    out["month"] = pd.to_datetime(dict(year=year, month=out["m"], day=1))
    out["net_sales"] = out["net_sales"].round(2)
    return out[["month", "entity_name", "net_sales"]].dropna(subset=["entity_name"])


# --------------------------------------------------------------------------- FR-05
def area_sales(conn, start: date, end: date) -> pd.DataFrame:
    df = _query(conn, """
        SELECT delivery_area, ROUND(SUM(net_sales),2) AS net_sales,
               COUNT(DISTINCT order_id) AS orders, SUM(units_sold) AS units_sold
        FROM v_item_facts WHERE order_date BETWEEN ? AND ?
        GROUP BY delivery_area ORDER BY net_sales DESC, orders DESC, delivery_area ASC""",
                 _params(start, end))
    return _add_rank(df)


# --------------------------------------------------------------------------- FR-06 / FR-07
def product_profitability(conn, start: date, end: date) -> pd.DataFrame:
    """One row per product that had valid sales lines in the period (unranked)."""
    df = _query(conn, """
        SELECT product_name, brand, product_type, SUM(units_sold) AS units_sold,
               ROUND(SUM(net_sales),2) AS net_sales, ROUND(SUM(product_cost),2) AS product_cost
        FROM v_item_facts WHERE order_date BETWEEN ? AND ?
        GROUP BY product_id""", _params(start, end))
    return _add_profit_cols(df)


def most_profitable(conn, start: date, end: date, limit: int | None = 10) -> pd.DataFrame:
    df = product_profitability(conn, start, end).sort_values(
        ["profit", "net_sales", "product_name"], ascending=[False, False, True])
    return _add_rank(df.head(limit) if limit else df)


def loss_making(conn, start: date, end: date, limit: int = 5) -> pd.DataFrame:
    """Up to `limit` products with negative total profit, worst first. May return < limit rows."""
    df = product_profitability(conn, start, end)
    df = df[df["profit"] < 0].sort_values(["profit", "net_sales", "product_name"],
                                          ascending=[True, False, True])
    return _add_rank(df.head(limit))


# --------------------------------------------------------------------------- FR-08
def sales_by_type_over_time(conn, start: date, end: date, grain: str) -> pd.DataFrame:
    expr = GRAINS[grain]
    return _query(conn, f"""
        SELECT {expr} AS period_start, product_type, ROUND(SUM(net_sales),2) AS net_sales,
               SUM(units_sold) AS units_sold
        FROM v_item_facts WHERE order_date BETWEEN ? AND ?
        GROUP BY period_start, product_type ORDER BY period_start, product_type""",
                  _params(start, end))


# --------------------------------------------------------------------------- FR-09
def beverage_share(conn, start: date, end: date) -> pd.DataFrame:
    df = _query(conn, """
        SELECT product_name, ROUND(SUM(net_sales),2) AS net_sales, SUM(units_sold) AS units_sold
        FROM v_item_facts WHERE product_type = 'Beverages' AND order_date BETWEEN ? AND ?
        GROUP BY product_id ORDER BY net_sales DESC, product_name ASC""", _params(start, end))
    total = df["net_sales"].sum()
    # A product whose net sales are <= 0 cannot be a pie slice; drop and let caller note it.
    df = df[df["net_sales"] > 0].copy()
    df["share_pct"] = (df["net_sales"] / df["net_sales"].sum() * 100).round(2) if len(df) else []
    return _add_rank(df)


# --------------------------------------------------------------------------- misc
def data_date_range(conn) -> tuple[date, date] | None:
    lo, hi = conn.execute("SELECT MIN(date(order_datetime)), MAX(date(order_datetime)) "
                          "FROM orders").fetchone()
    return (date.fromisoformat(lo), date.fromisoformat(hi)) if lo else None
