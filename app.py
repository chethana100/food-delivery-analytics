"""Food Delivery Sales & Profit Analytics - Streamlit dashboard.

Run:  streamlit run app.py
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from src import analytics as an
from src import config, db, periods
from src.generate_data import build_database
from src.validation import check_database

st.set_page_config(page_title="Food Delivery Analytics", page_icon="🍔", layout="wide")


# ----------------------------------------------------------------------------- helpers
def inr(x, decimals: int = 0) -> str:
    """Format as ₹ with Indian digit grouping (12,34,567)."""
    if x is None or pd.isna(x):
        return "N/A"
    sign = "-" if x < 0 else ""
    s = f"{abs(x):.{decimals}f}"
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return f"{sign}{config.CURRENCY}{whole}" + (f".{frac}" if frac else "")


def show_table(df: pd.DataFrame, name: str, money=(), pct=(), key: str = ""):
    """Display a ranked table with ₹ formatting + CSV download of the raw numbers."""
    disp = df.copy()
    for c in money:
        disp[c] = disp[c].map(lambda v: inr(v, 2))
    for c in pct:
        disp[c] = disp[c].map(lambda v: "N/A" if v is None or pd.isna(v) else f"{v:.1f}%")
    st.dataframe(disp, hide_index=True, width="stretch")
    st.download_button("⬇ CSV", df.to_csv(index=False).encode(), f"{name}.csv", "text/csv",
                       key=f"dl_{key or name}")


def money_axis(fig, axis="y"):
    getattr(fig, f"update_{axis}axes")(tickprefix=config.CURRENCY, tickformat=",")
    return fig


@st.cache_resource(show_spinner="Preparing database…")
def get_conn():
    if not config.DB_PATH.exists():
        build_database()
    return db.connect()


conn = get_conn()
bounds = an.data_date_range(conn)

# ----------------------------------------------------------------------------- sidebar
st.sidebar.header("Reporting period")
today = periods.today_local()
default_as_of = min(today, bounds[1]) if bounds else today
as_of = st.sidebar.date_input("As-of date", default_as_of,
                              help="'Current' week/month/year are calculated around this date. "
                                   "Defaults to today (IST), capped at the last date in the data.")
choice = st.sidebar.radio("Period", periods.PERIOD_CHOICES, index=2)
custom = None
if choice == "Custom range":
    picked = st.sidebar.date_input("From – To", (as_of.replace(day=1), as_of))
    if isinstance(picked, tuple) and len(picked) == 2:
        custom = picked
    else:
        st.sidebar.info("Pick both a start and an end date.")
        custom = (as_of, as_of)
start, end = periods.resolve_period(choice, as_of, custom)
period_label = f"{choice}: {periods.format_range(start, end)}"

st.sidebar.divider()
st.sidebar.caption(f"All dates in {config.REPORTING_TZ}. Weeks run Monday–Sunday. "
                   f"Currency: INR ({config.CURRENCY}).")
if bounds:
    st.sidebar.caption(f"Data available: {periods.format_range(*bounds)}")
with st.sidebar.expander("Data quality"):
    st.dataframe(check_database(conn), hide_index=True, width="stretch")
with st.sidebar.expander("Definitions"):
    st.markdown(
        "- **Net sales** = qty × price − discount − refund (cancelled orders excluded)\n"
        "- **Units sold** = qty − returned qty\n"
        "- **Product cost** = (qty − returned qty) × unit cost\n"
        "- **Profit** = net sales − product cost. *Simplified: excludes delivery, packaging, "
        "commissions and overheads.*\n"
        "- **Margin** = profit ÷ net sales × 100 (N/A if net sales ≤ 0)\n"
        "- **Ties** are broken by the secondary metric, then name A→Z.")

# ----------------------------------------------------------------------------- header + cards
st.title("🍔 Food Delivery – Sales & Profit Dashboard")
st.markdown(f"**Reporting period:** {period_label}")

s = an.summary(conn, start, end)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Net sales", inr(s["net_sales"]))
c2.metric("Orders", f"{s['orders']:,}")
c3.metric("Units sold", f"{s['units']:,}")
c4.metric("Total product profit", inr(s["profit"]),
          help="Simplified: net sales − product cost.")

if s["orders"] == 0:
    st.warning("No sales found for this period. Try another period or as-of date"
               + (f" (data covers {periods.format_range(*bounds)})." if bounds else "."))
    st.stop()

# ----------------------------------------------------------------------------- FR-01
st.header("1 · Top brand this month")
m_start, m_end = periods.month_range(as_of)
st.caption(f"Ranked by net sales · {periods.format_range(m_start, m_end)} "
           f"(calendar month of the as-of date)")
brands = an.top_brands(conn, m_start, m_end)
if brands.empty:
    st.info("No sales in this calendar month.")
else:
    b = brands.iloc[0]
    st.success(f"**{b.brand}** leads with {inr(b.net_sales)} net sales and {int(b.units_sold):,} units.")
    left, right = st.columns([2, 3])
    with left:
        show_table(brands, "top_brands_month", money=["net_sales"], key="brands")
    with right:
        fig = px.bar(brands, x="brand", y="net_sales", hover_data=["units_sold"],
                     title=f"Net sales by brand – {m_start:%B %Y}",
                     labels={"brand": "Brand", "net_sales": "Net sales (₹)"})
        st.plotly_chart(money_axis(fig), width="stretch")

# ----------------------------------------------------------------------------- FR-02
st.header("2 · Best-selling product")
st.caption("Ranked by **units sold** (net of returns); net sales shown as secondary. "
           "Ties: higher net sales first, then name A→Z.")
tabs = st.tabs(["Current week", "Current month", "Current year"])
for tab, (label, rng) in zip(tabs, [("week", periods.week_range(as_of)),
                                    ("month", periods.month_range(as_of)),
                                    ("year", periods.year_range(as_of))]):
    with tab:
        st.caption(periods.format_range(*rng))
        best = an.best_selling_products(conn, *rng, limit=10)
        if best.empty:
            st.info(f"No sales in the current {label}.")
        else:
            t = best.iloc[0]
            st.success(f"**{t.product_name}** – {int(t.units_sold):,} units, {inr(t.net_sales)} net sales")
            show_table(best, f"best_selling_{label}", money=["net_sales"], key=f"best_{label}")

# ----------------------------------------------------------------------------- FR-03 / FR-04
st.header("3 & 4 · Top-five trends by month")
years = sorted({int(y) for y in pd.read_sql_query(
    "SELECT DISTINCT strftime('%Y', order_date) y FROM v_item_facts", conn)["y"]})
year = st.selectbox("Calendar year", years,
                    index=years.index(start.year) if start.year in years else len(years) - 1)
through = as_of.month if year == as_of.year else 12
st.caption("Top five are selected by **total net sales over the whole calendar year** "
           "(ties: units, then name); each line is that item's monthly net sales. "
           "Months with no sales show ₹0." + (" Current year is shown up to the as-of month."
                                              if through < 12 else ""))
for ent, title, ent_label in [("product", "Top-5 products", "Product"),
                              ("customer", "Top-5 customers", "Customer")]:
    top = an.top_entities(conn, ent, year, 5)
    st.subheader(f"{title} – {year}")
    if top.empty:
        st.info(f"No sales in {year}.")
        continue
    trend = an.monthly_trend(conn, ent, year, list(top.entity_id), through)
    cl, cr = st.columns([2, 3])
    with cl:
        show_table(top.drop(columns="entity_id").rename(columns={"entity_name": ent_label.lower()}),
                   f"top5_{ent}s_{year}", money=["net_sales"], key=f"top5_{ent}")
    with cr:
        fig = px.line(trend, x="month", y="net_sales", color="entity_name", markers=True,
                      title=f"Monthly net sales – {title.lower()} ({year})",
                      labels={"month": "Month", "net_sales": "Net sales (₹)", "entity_name": ent_label})
        fig.update_xaxes(dtick="M1", tickformat="%b")
        st.plotly_chart(money_axis(fig), width="stretch")

# ----------------------------------------------------------------------------- FR-05
st.header("5 · Highest-sales delivery area")
st.caption(f"Net sales by delivery area · {period_label}. Orders with no area appear as 'Unknown'.")
areas = an.area_sales(conn, start, end)
a = areas.iloc[0]
st.success(f"**{a.delivery_area}** leads with {inr(a.net_sales)} net sales ({int(a.orders):,} orders).")
cl, cr = st.columns([2, 3])
with cl:
    show_table(areas, "area_sales", money=["net_sales"], key="areas")
with cr:
    fig = px.bar(areas, x="net_sales", y="delivery_area", orientation="h",
                 title=f"Net sales by delivery area ({periods.format_range(start, end)})",
                 labels={"net_sales": "Net sales (₹)", "delivery_area": "Delivery area"})
    fig.update_yaxes(categoryorder="total ascending")
    st.plotly_chart(money_axis(fig, "x"), width="stretch")

# ----------------------------------------------------------------------------- FR-06 / FR-07
st.header("6 & 7 · Product profitability")
st.caption(f"{period_label}. Profit = net sales − product cost (simplified; excludes delivery, "
           f"packaging, commissions, overheads).")
cl, cr = st.columns(2)
with cl:
    st.subheader("Most profitable products")
    mp = an.most_profitable(conn, start, end, 10)
    top = mp.iloc[0]
    st.success(f"**{top.product_name}** – profit {inr(top.profit)} on {inr(top.net_sales)} sales "
               f"({'N/A' if pd.isna(top.margin_pct) else f'{top.margin_pct:.1f}%'} margin)")
    show_table(mp[["rank", "product_name", "profit", "net_sales", "margin_pct"]],
               "most_profitable", money=["profit", "net_sales"], pct=["margin_pct"], key="mp")
with cr:
    st.subheader("Top 5 loss-making products")
    lm = an.loss_making(conn, start, end, 5)
    if lm.empty:
        st.info("No product made a loss in this period.")
    else:
        if len(lm) < 5:
            st.info(f"Only {len(lm)} product(s) made a loss in this period.")
        show_table(lm[["rank", "product_name", "profit", "net_sales", "margin_pct"]],
                   "loss_making", money=["profit", "net_sales"], pct=["margin_pct"], key="lm")
        fig = px.bar(lm, x="product_name", y="profit", title="Loss by product (most negative first)",
                     labels={"product_name": "Product", "profit": "Total profit (₹)"})
        fig.update_traces(marker_color="#d62728")
        st.plotly_chart(money_axis(fig), width="stretch")

# ----------------------------------------------------------------------------- FR-08
st.header("8 · Product-type sales over time")
grain = st.radio("Time grain", list(an.GRAINS), horizontal=True, index=2)
st.caption(f"Net sales by product type · {period_label} · {grain.lower()} buckets "
           f"({'Monday-start weeks' if grain == 'Weekly' else 'calendar periods'}; the first/last "
           f"bucket may be partial if the period cuts through it).")
ts = an.sales_by_type_over_time(conn, start, end, grain)
if ts.empty:
    st.info("No sales for this period.")
else:
    ts["period_start"] = pd.to_datetime(ts["period_start"])
    fig = px.bar(ts, x="period_start", y="net_sales", color="product_type",
                 title=f"{grain} net sales by product type",
                 labels={"period_start": {"Daily": "Day", "Weekly": "Week starting (Mon)",
                                          "Monthly": "Month", "Yearly": "Year"}[grain],
                         "net_sales": "Net sales (₹)", "product_type": "Product type"})
    fmt = {"Daily": "%d %b", "Weekly": "%d %b", "Monthly": "%b %Y", "Yearly": "%Y"}[grain]
    fig.update_xaxes(tickformat=fmt)
    st.plotly_chart(money_axis(fig), width="stretch")
    with st.expander("Table"):
        show_table(ts.assign(period_start=ts.period_start.dt.date), f"sales_by_type_{grain.lower()}",
                   money=["net_sales"], key="ts")

# ----------------------------------------------------------------------------- FR-09
st.header("9 · Beverages – share of net sales")
bev = an.beverage_share(conn, start, end)
if bev.empty:
    st.info(f"No beverage sales for {periods.format_range(start, end)}.")
else:
    cl, cr = st.columns([3, 2])
    with cl:
        fig = px.pie(bev, names="product_name", values="net_sales",
                     title=f"Beverages: share of net sales by product ({periods.format_range(start, end)})")
        fig.update_traces(textinfo="label+percent",
                          hovertemplate="%{label}<br>₹%{value:,.0f} (%{percent})<extra></extra>")
        st.plotly_chart(fig, width="stretch")
    with cr:
        show_table(bev, "beverage_share", money=["net_sales"], pct=["share_pct"], key="bev")

st.divider()
st.caption("Learning exercise with synthetic data – not an accounting system.")
