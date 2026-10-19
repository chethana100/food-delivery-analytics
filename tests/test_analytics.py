"""Edge cases required by the BRD (section 9) plus ranking/period checks."""
from datetime import date

import pandas as pd
import pytest

from src import analytics as an

D = date
WIDE = (D(2025, 1, 1), D(2026, 12, 31))


def item(product, qty, price, cost, **kw):
    return dict(product=product, qty=qty, price=price, cost=cost, **kw)


def test_cancelled_orders_do_not_inflate_sales(b):
    b.product(1, "Burger")
    b.order("2026-03-01", [item(1, 2, 100, 40)])
    b.order("2026-03-02", [item(1, 10, 100, 40)], status="Cancelled")
    s = an.summary(b.conn, *WIDE)
    assert s == {"net_sales": 200.0, "orders": 1, "units": 2, "profit": 120.0}


def test_discount_and_refund_reduce_net_sales_and_profit(b):
    b.product(1, "Burger")
    # gross 300, discount 30, partial refund 100 for 1 returned unit (cost restocked)
    b.order("2026-03-01", [item(1, 3, 100, 40, disc=30, refund=100, ret=1)])
    s = an.summary(b.conn, *WIDE)
    assert s["net_sales"] == 170.0          # 300 - 30 - 100
    assert s["units"] == 2                  # 3 - 1 returned
    assert s["profit"] == 170 - 2 * 40      # cost only for kept units


def test_negative_profit_product_in_loss_list_and_fewer_than_five(b):
    b.product(1, "Loss Leader")
    b.product(2, "Winner")
    b.order("2026-03-01", [item(1, 1, 100, 130), item(2, 1, 100, 40)])
    loss = an.loss_making(b.conn, *WIDE, limit=5)
    assert list(loss.product_name) == ["Loss Leader"]      # only 1 of up-to-5 shown
    assert loss.iloc[0].profit == -30
    assert loss.iloc[0].margin_pct == pytest.approx(-30.0)


def test_no_losses_returns_empty(b):
    b.product(1, "Winner")
    b.order("2026-03-01", [item(1, 1, 100, 40)])
    assert an.loss_making(b.conn, *WIDE).empty


def test_zero_sales_product_margin_is_na_not_crash(b):
    b.product(1, "Fully Refunded")
    # full return: net sales 0, cost 0 -> margin undefined
    b.order("2026-03-01", [item(1, 2, 50, 20, refund=100, ret=2)])
    row = an.product_profitability(b.conn, *WIDE).iloc[0]
    assert row.net_sales == 0 and row.profit == 0
    assert pd.isna(row.margin_pct)
    assert an.margin_pct(0, 0) is None and an.margin_pct(-5, -10) is None
    assert an.margin_pct(25, 100) == 25.0


def test_week_crossing_month_and_year_boundary(b):
    b.product(1, "Burger")
    b.order("2025-12-31", [item(1, 1, 100, 40)])   # Wed
    b.order("2026-01-02", [item(1, 1, 100, 40)])   # Fri, same Mon-Sun week
    b.order("2026-01-05", [item(1, 1, 100, 40)])   # next Monday
    wk = an.sales_by_type_over_time(b.conn, *WIDE, "Weekly")
    assert list(wk.period_start) == ["2025-12-29", "2026-01-05"]
    assert list(wk.net_sales) == [200.0, 100.0]
    mo = an.sales_by_type_over_time(b.conn, *WIDE, "Monthly")
    assert list(mo.period_start) == ["2025-12-01", "2026-01-01"]
    yr = an.sales_by_type_over_time(b.conn, *WIDE, "Yearly")
    assert list(yr.period_start) == ["2025-01-01", "2026-01-01"]
    day = an.sales_by_type_over_time(b.conn, *WIDE, "Daily")
    assert len(day) == 3


def test_sunday_belongs_to_week_that_started_monday(b):
    b.product(1, "Burger")
    b.order("2026-10-18", [item(1, 1, 100, 40)])   # Sunday
    b.order("2026-10-19", [item(1, 1, 100, 40)])   # Monday
    wk = an.sales_by_type_over_time(b.conn, *WIDE, "Weekly")
    assert list(wk.period_start) == ["2026-10-12", "2026-10-19"]


def test_best_seller_is_by_units_not_revenue(b):
    b.product(1, "Cheap Fries")
    b.product(2, "Party Box")
    b.order("2026-03-01", [item(1, 5, 20, 5), item(2, 1, 1000, 500)])
    best = an.best_selling_products(b.conn, *WIDE)
    assert best.iloc[0].product_name == "Cheap Fries"      # 5 units, ₹100
    assert best.iloc[1].product_name == "Party Box"        # 1 unit, ₹1000


def test_multi_item_order_not_double_counted(b):
    b.product(1, "A")
    b.product(2, "B")
    b.product(3, "C")
    b.order("2026-03-01", [item(1, 1, 100, 40), item(2, 1, 100, 40), item(3, 1, 100, 40)])
    b.order("2026-03-02", [item(1, 1, 100, 40)])
    s = an.summary(b.conn, *WIDE)
    assert s["orders"] == 2 and s["net_sales"] == 400.0
    assert an.area_sales(b.conn, *WIDE).iloc[0].orders == 2


def test_empty_period_gives_zero_summary_and_empty_frames(b):
    b.product(1, "A")
    b.order("2026-03-01", [item(1, 1, 100, 40)])
    nothing = (D(2024, 1, 1), D(2024, 1, 31))
    assert an.summary(b.conn, *nothing) == {"net_sales": 0.0, "orders": 0, "units": 0, "profit": 0.0}
    assert an.top_brands(b.conn, *nothing).empty
    assert an.best_selling_products(b.conn, *nothing).empty
    assert an.area_sales(b.conn, *nothing).empty
    assert an.most_profitable(b.conn, *nothing).empty
    assert an.beverage_share(b.conn, *nothing).empty
    assert an.sales_by_type_over_time(b.conn, *nothing, "Daily").empty
    assert an.top_entities(b.conn, "product", 2024).empty
    assert an.monthly_trend(b.conn, "product", 2024, []).empty


def test_ties_are_deterministic(b):
    for pid, name in [(1, "Zebra"), (2, "Apple"), (3, "Mango")]:
        b.product(pid, name)
    # identical units; Mango has higher net sales, Apple/Zebra tie fully -> name A..Z
    b.order("2026-03-01", [item(1, 2, 100, 10), item(2, 2, 100, 10), item(3, 2, 150, 10)])
    best = an.best_selling_products(b.conn, *WIDE)
    assert list(best.product_name) == ["Mango", "Apple", "Zebra"]
    assert list(best["rank"]) == [1, 2, 3]


def test_beverage_pie_only_beverages_and_selected_period(b):
    b.product(1, "Cola", ptype="Beverages")
    b.product(2, "Chai", ptype="Beverages")
    b.product(3, "Burger", ptype="Burgers")
    b.order("2026-03-10", [item(1, 1, 60, 20), item(2, 1, 40, 10), item(3, 1, 500, 100)])
    b.order("2026-05-10", [item(1, 1, 999, 20)])                       # outside period
    bev = an.beverage_share(b.conn, D(2026, 3, 1), D(2026, 3, 31))
    assert set(bev.product_name) == {"Cola", "Chai"}
    assert bev.share_pct.sum() == pytest.approx(100.0)
    assert bev.set_index("product_name").loc["Cola", "share_pct"] == 60.0


def test_top_five_selection_and_monthly_zero_fill(b):
    for pid in range(1, 8):
        b.product(pid, f"P{pid}")
    # P1..P7 with strictly decreasing sales; P1 sells only in March, P2 in Jan + March
    b.order("2026-03-05", [item(p, 1, 1000 - p * 100, 1) for p in range(1, 8)])
    b.order("2026-01-05", [item(2, 1, 50, 1)])
    top = an.top_entities(b.conn, "product", 2026, 5)
    assert list(top.entity_name) == ["P1", "P2", "P3", "P4", "P5"]
    tr = an.monthly_trend(b.conn, "product", 2026, list(top.entity_id), through_month=4)
    p1 = tr[tr.entity_name == "P1"].sort_values("month")
    assert list(p1.net_sales) == [0.0, 0.0, 900.0, 0.0]          # every month present, zero-filled
    assert len(tr) == 5 * 4


def test_top_customers_use_net_sales_and_year(b):
    b.product(1, "A")
    b.order("2026-03-01", [item(1, 1, 100, 10)], customer="C1")
    b.order("2026-03-02", [item(1, 3, 100, 10)], customer="C2")
    b.order("2025-03-02", [item(1, 50, 100, 10)], customer="C1")        # other year
    top = an.top_entities(b.conn, "customer", 2026)
    assert list(top.entity_id) == ["C2", "C1"]
    assert "Test Two" in top.iloc[0].entity_name


def test_missing_area_reported_as_unknown(b):
    b.product(1, "A")
    b.order("2026-03-01", [item(1, 1, 100, 10)], area=None)
    b.order("2026-03-01", [item(1, 1, 100, 10)], area="  ")
    areas = an.area_sales(b.conn, *WIDE)
    assert list(areas.delivery_area) == ["Unknown"] and areas.iloc[0].orders == 2


def test_period_bounds_are_inclusive(b):
    b.product(1, "A")
    b.order("2026-03-01", [item(1, 1, 100, 10)])
    b.order("2026-03-31", [item(1, 1, 100, 10)])
    b.order("2026-04-01", [item(1, 1, 100, 10)])
    assert an.summary(b.conn, D(2026, 3, 1), D(2026, 3, 31))["orders"] == 2
