# Food Delivery – Sales & Profit Analytics

A small Streamlit dashboard that turns order-level data for a fictional food-delivery company into
trustworthy sales and profit insights. Built for the *Food Delivery Analytics Hackathon BRD*;
all nine business questions (FR-01 … FR-09) are answered from the data — nothing is hard-coded.

> Learning exercise with **synthetic data only**. Profit is a *simplified product-level* figure, not accounting.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate     # optional
pip install -r requirements.txt
python -m src.generate_data        # (re)builds data/food_delivery.db with seed 42 – optional, DB is included
streamlit run app.py               # opens http://localhost:8501
pytest                             # 26 tests
```
Docker: `docker build -t fd-analytics . && docker run -p 8501:8501 fd-analytics`.

If `data/food_delivery.db` is missing, the app generates it on first start.
The period is changed from the sidebar (as-of date, current week / month / year, or custom range) – no code edits needed.

## Where each requirement lives

| ID | Dashboard section | Query (`src/analytics.py`) |
|----|-------------------|----------------------------|
| FR-01 Top brand this month | 1 | `top_brands` (calendar month of the as-of date) |
| FR-02 Best-selling product | 2 (week/month/year tabs) | `best_selling_products` – ranked by **units**, net sales secondary |
| FR-03 Top-5 product trend | 3 & 4 | `top_entities("product")` + `monthly_trend` |
| FR-04 Top-5 customer trend | 3 & 4 | `top_entities("customer")` + `monthly_trend` |
| FR-05 Highest-sales area | 5 | `area_sales` |
| FR-06 Most profitable product | 6 & 7 | `most_profitable` |
| FR-07 Top-5 loss-makers | 6 & 7 | `loss_making` (shows fewer than 5 + a message if fewer exist) |
| FR-08 Type sales over time | 8 (daily/weekly/monthly/yearly selector) | `sales_by_type_over_time` |
| FR-09 Beverage pie | 9 | `beverage_share` (only `product_type = 'Beverages'`) |

Summary cards (net sales, orders, units, profit), CSV downloads on every ranked table, a data-quality panel and
a definitions panel are in the page / sidebar. Empty periods show a warning instead of crashing.

## Architecture

```
app.py                 Streamlit UI only (formatting, charts, widgets)
src/analytics.py       one function per business question; SQL aggregation + small pandas post-processing
src/periods.py         week/month/year boundaries (Mon–Sun weeks, IST)
src/validation.py      row cleaning (rejects with reasons) + database quality checks
src/generate_data.py   seeded synthetic data → CSV + SQLite
sql/schema.sql         tables, constraints, indexes and the v_item_facts view
tests/                 pytest suite
data/                  generated CSVs, SQLite DB, rejected_rows.csv
```

### Data model
`customers (customer_id PK, customer_name)` · `products (product_id PK, name, brand, product_type)` ·
`orders (order_id PK, order_datetime, customer_id FK, delivery_area, order_status)` ·
`order_items (order_item_id PK, order_id FK, product_id FK, quantity, unit_selling_price, discount_amount,
refund_amount, returned_quantity, unit_product_cost)`.
CHECK constraints reject non-positive quantities, negative prices, and `returned_quantity > quantity`.
Brand/category live only on `products`, so they can't drift between order lines.

**One view defines every metric.** `v_item_facts` has one row per *non-cancelled* order line with `net_sales`,
`units_sold` and `product_cost`. Every report aggregates from it, so definitions can't differ between queries, and
there is no order-level amount to multiply when orders are joined to items. Order count uses `COUNT(DISTINCT order_id)`.

### What is done in SQL vs Python
SQL: date filtering, joins, `SUM`/`COUNT`, grouping by day/week/month/year, deterministic `ORDER BY`.
Python: margin (division guard), rank numbers, zero-filling missing months in trend lines, formatting.
Reason: aggregation belongs next to the data; guarded division and presentation are easier to test in Python.

## Definitions & assumptions

| Term | Rule |
|------|------|
| Net sales | `quantity × unit price − discount − refund`; cancelled orders excluded entirely |
| Units sold | `quantity − returned_quantity` |
| Product cost | `(quantity − returned_quantity) × unit cost` — returned goods are assumed **restocked**, so their cost is not incurred |
| Profit | `net sales − product cost` (excludes delivery, packaging, commissions, overheads) |
| Margin | `profit ÷ net sales × 100`; **N/A when net sales ≤ 0** (zero *or* negative) |
| Refund without return | (e.g. compensation) reduces net sales but cost stays, so profit falls |
| Refund on a cancelled order | none exist; cancelled orders are dropped before any amount is used |
| Best-selling | units sold; tie → higher net sales → name A–Z |
| Other ranking ties | secondary metric (see `analytics.py` docstring) → name A–Z; `rank` is row position, so tied rows get consecutive ranks |
| Top-5 products/customers | by total **net sales over the selected calendar year**; same 5 are plotted for every month; empty months plotted as ₹0 |
| Week | Monday–Sunday. A week spanning New Year is one bucket (e.g. Mon 29 Dec 2025 – Sun 4 Jan 2026) in the weekly grain; with a period filter the first/last bucket may be partial |
| Timezone | all timestamps stored as naive ISO strings in `Asia/Kolkata`; "today" computed in IST |
| Missing area | shown as `Unknown` (not dropped) |
| Beverage pie | only products with net sales > 0 in the period can form a slice |
| "Current" periods | calculated around the sidebar **as-of date**, which defaults to today (IST) capped at the latest date in the data |
| FR-01 | always the calendar month of the as-of date, independent of the sidebar period (as the BRD says "this month") |
| FR-08 | uses the sidebar period as its date range, with its own grain selector |

## Dataset

Seed 42, 1 Jan 2025 – 17 Oct 2026: ~15.5k orders, ~31k order items, 140 customers, 38 products, 9 brands,
7 categories (8 beverages), 6 areas. ~4% orders cancelled, ~3% of items with refund/returns, ~30% of lines discounted.
Realism: weekend peaks, lunch/dinner hours, ~60% growth over the span, a price rise from April 2026, heavy-tailed
customer spend, mostly-stable customer home areas.
Designed-in patterns for the analysis: six products sold below cost (promo "loss leaders"), and two
high-ticket, low-volume items (party boxes) to prove units ≠ revenue.
25 orders have a blank area and 15 deliberately dirty item rows (duplicates, zero/negative quantity, bad price,
orphan order) are injected, then **rejected with a reason** into `data/rejected_rows.csv`.

## Tests (`pytest`)
Cover every BRD §9 edge case: cancelled orders, discount/refund rule, loss-maker listing (and < 5 case), zero-sales
margin N/A, week across month/year boundary (+ Sunday/Monday boundary), units-vs-revenue winner, no double counting
when joining orders to many items, empty period, deterministic ties, beverage-only/period-only pie, top-5 selection
with zero-filled months, inclusive date bounds, plus period helpers, cleaning rules, schema constraints,
generator reproducibility and dataset-size requirements.

## Insights (seeded data, 1 Jan – 17 Oct 2026; re-check in the app)
1. **Six products sell below cost.** Cheese Burst Pizza (−₹28,967), Mini Burger Trio (−₹18,117), Red Velvet Cake Slice
   (−₹12,430), Protein Smoothie Bowl (−₹10,309), Onion Rings (−₹7,460) and Sparkling Water (−₹4,614) lose ₹81,897 in
   total – about 4% of the ₹19.3 lakh total profit. Cheese Burst Pizza alone moves ₹1.36 lakh of sales at −21% margin
   – reprice or stop discounting these first. (Caveat: if they are intentional traffic-drivers, test whether baskets with them are larger.)
2. **Units and revenue point to different products.** French Fries is #1 by units (1,332) but Chicken Dum Biryani
   is #1 by net sales (₹3.45 lakh) *and* by profit (₹1.65 lakh, 48% margin) on 1,204 units. Promote biryani, not fries, to grow profit.
3. **Demand is concentrated in time and place.** Fri–Sun produce ~51% of net sales, and Indiranagar + Koramangala
   ~43%. Staff riders and kitchen capacity accordingly; Whitefield (lowest) is the area to investigate.
4. **Growth is strong:** net sales are +37% vs the same 1 Jan–17 Oct window of 2025. Top-10 of 140 customers
   contribute ~32% of sales, so retention of heavy buyers matters.

## Known limitations
- Profit ignores delivery, packaging, commissions, overheads; cost is a single unit cost per line (no cost history).
- SQLite, single process; the UI queries live. Fine at 30k rows; see scaling note below.
- Customer names are synthetic and can coincide; the customer ID is the identity.
- Currency is fixed at INR; no tax handling; discounts are given per line (no order-level allocation needed).
- Partial weekly/monthly buckets at period edges are not flagged on the chart.
- Streamlit date-input "custom range" needs both dates picked before results update.

## With another day
Period-over-period comparison and % change; category → brand → product drill-down; materialised daily aggregate
table; chart annotations for partial buckets; CI running pytest; AI-narrative layer fed only from computed tables.

### Scaling 10k → 100M order items
Move to PostgreSQL (partitioned by month) or a columnar store; pre-aggregate daily facts by product/customer/area
and query those; index/cluster on date; cache query results; keep top-N with window functions in SQL rather than
loading frames into pandas.
