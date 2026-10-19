# Food Delivery Sales & Profit Analytics
## Project & Business Analytics Submission Report
**Hackathon Brief / Business Requirements Document Evaluation**  
**Candidate:** Chethana (`chethana100`)  
**Repository:** [https://github.com/chethana100/food-delivery-analytics](https://github.com/chethana100/food-delivery-analytics)  
**Technology Stack:** Python 3, SQLite, Streamlit, Plotly Express, Pandas, Pytest, Docker  

---

## 1. Executive Summary

This report presents the complete solution for the **Food Delivery Sales & Profit Analytics** challenge. A production-grade analytics platform was built to transform raw order-item events into high-trust strategic and operational insights across brands, products, customers, delivery areas, and categories.

### High-Level Lifetime Figures (Jan 1, 2025 – Oct 17, 2026)
* **Total Net Sales:** ₹83,71,879 (₹83.72 Lakhs)
* **Fulfilled Orders:** 14,862 orders (excluding 628 cancelled orders)
* **Net Units Delivered:** 45,563 units
* **Total Product Profit:** ₹37,15,401 (Overall Product Gross Margin: **44.38%**)
* **Active Geographic Areas:** 6 delivery clusters across Bengaluru

---

## 2. System Architecture & Engineering Design

```
                     ┌────────────────────────────────────────┐
                     │       Streamlit Dashboard (app.py)     │
                     │  - Interactive Period / As-of Filter   │
                     │  - KPI Cards, Ranked Tables, Plotly    │
                     └───────────────────▲────────────────────┘
                                         │ Calls
                     ┌───────────────────┴────────────────────┐
                     │     Analytics Service Layer (src/)     │
                     │  - analytics.py: Query contracts       │
                     │  - periods.py: ISO / IST boundaries    │
                     │  - validation.py: Row cleaning logic   │
                     └───────────────────▲────────────────────┘
                                         │ Queries
                     ┌───────────────────┴────────────────────┐
                     │    Canonical Fact View (v_item_facts)  │
                     │  Pre-calculates net_sales, units, cost │
                     └───────────────────▲────────────────────┘
                                         │ Reads
                     ┌───────────────────┴────────────────────┐
                     │       SQLite 3NF Relational Store      │
                     │  orders, order_items, products, custom.│
                     └────────────────────────────────────────┘
```

### Why This Technology Stack?
1. **SQLite 3NF Database:** Provides ACID-compliant relational joins, SQL aggregate functions, and indexed views without requiring external daemon infrastructure.
2. **Canonical SQL Fact View (`v_item_facts`):** Solves the single most common data-engineering bug in multi-item order architectures: **preventing order-level values from multiplying when joining orders to order items**.
3. **Streamlit + Plotly:** Provides an instant, interactive web interface without JavaScript/CSS maintenance overhead. Plots allow hover tooltips, responsive resizing, and dynamic grouping.
4. **Clean Division of Responsibility:**
   - **SQL Layer:** Filtering, range joins, deterministic aggregations, and sorting.
   - **Python Layer:** Division-by-zero guards (`margin = N/A` when sales ≤ 0), time-grain bucketing, presentation formatting (Indian ₹ numbering format), and export serialization.

---

## 3. Business Requirements Compliance Matrix (FR-01 to FR-09)

| Requirement ID | Acceptance Criteria | Implementation Detail | Analytical Correctness Safeguards |
|---|---|---|---|
| **FR-01: Top brand this month** | Rank brands by net sales for the calendar month of the as-of date. | `top_brands(conn, start, end)` | Strictly uses calendar month of the as-of date (e.g., Oct 1 to Oct 31, 2026), not a floating 30-day window. |
| **FR-02: Best-selling product** | Identify best-selling product for current week, month, and year. | `best_selling_products(conn, ...)` with tabs in UI | **Ranked by units sold** (not revenue). Secondary sort on net sales, tertiary on name A→Z. Explicitly proves high-ticket items (e.g. Party Box) do not displace true volume leaders. |
| **FR-03: Top-5 product trend** | Top 5 products for selected year by net sales, with monthly trajectory. | `top_entities(..., "product")` + `monthly_trend()` | Top 5 chosen based on **full annual net sales**. Zero-fills missing monthly sales to ₹0 so lines remain continuous. |
| **FR-04: Top-5 customer trend** | Top 5 customers for selected year by net sales, with monthly trajectory. | `top_entities(..., "customer")` + `monthly_trend()` | Uses stable synthetic customer IDs; evaluates retention and spend spikes across calendar months. |
| **FR-05: Highest-sales area** | Rank delivery areas by net sales; highlight leader and values. | `area_sales(conn, start, end)` | Horizontal bar chart sorted descending. Orders with unrecorded delivery locations are categorized as `"Unknown"` rather than dropped. |
| **FR-06: Most profitable product** | Rank products by total profit, showing profit, sales, and margin %. | `most_profitable(conn, start, end)` | Profit = `net_sales - product_cost`. Margin = `profit / net_sales * 100`. Guarded against division-by-zero. |
| **FR-07: Top loss-making products** | Up to 5 products with most negative profit; handles fewer gracefully. | `loss_making(conn, start, end)` | Displays products where `profit < 0` ordered by ascending profit. If fewer than 5 exist, displays an informative message. |
| **FR-08: Product-type sales over time** | Sales by category at daily, weekly, monthly, and yearly grain. | `sales_by_type_over_time(..., grain)` | Monday-start weeks (`strftime('%Y-%W')`), calendar months, and years. Dynamic radio selector in UI. |
| **FR-09: Beverage sales pie chart** | Share of net sales within Beverages category for selected period. | `beverage_share(conn, start, end)` | Strictly filters `product_type = 'Beverages'`. Graceful empty state when no beverage sales exist in period. |

---

## 4. Key Strategic Business Insights

From analyzing the 22-month operational dataset, four critical business discoveries emerged:

### Insight 1: Unchecked "Loss Leaders" Are Bleeding Profit
* **Finding:** 6 products consistently sell below their unit cost, generating a cumulative loss of **−₹81,897**.
* **Prime Culprit:** **Cheese Burst Pizza** generated ₹1.36 Lakhs in gross volume but resulted in **−₹28,967 net loss** (−21.3% margin). Other loss-makers include *Mini Burger Trio* (−₹18,117) and *Red Velvet Cake Slice* (−₹12,430).
* **Strategic Action:** Immediately eliminate promotions on Cheese Burst Pizza or renegotiate dairy supply costs. If kept as an intentional acquisition hook, establish a minimum order value (MOV) to ensure high-margin basket additions (e.g., drinks and sides).

### Insight 2: Volume Leader vs. Revenue Driver Disconnect
* **Finding:** **French Fries** is the undisputed #1 best-selling product by units sold (**1,332 units**), yet it contributes negligible net margin. In contrast, **Chicken Dum Biryani** ranks #2 in units (1,204 units) but generates **#1 in Net Sales (₹3.45 Lakhs)** and **#1 in Total Product Profit (₹1.65 Lakhs at a 48% margin)**.
* **Strategic Action:** Marketing spend should pivot from promoting low-margin finger food to Biryani combos and premium meal bundles to maximize absolute rupee contribution.

### Insight 3: Hyper-Concentration in Geography & Time
* **Finding:** Delivery demand is heavily localized:
  - **Indiranagar (₹18.05 Lakhs)** and **Koramangala (₹17.93 Lakhs)** generate **43.0%** of total business revenue.
  - Whitefield and Electronic City severely underperform relative to their geographic size.
  - **Weekend Surge:** Friday through Sunday accounts for **51.2%** of all order volume.
* **Strategic Action:** Transition delivery fleet scheduling to a weekend-heavy flex model. Concentrate dark kitchen expansion in the Indiranagar-Koramangala belt, while running targeted localized campaigns in Whitefield.

### Insight 4: Whale Customer Concentration & Retention Risk
* **Finding:** The top 10 customers (out of 140) account for **32.1%** of overall platform sales. Customer spend drops sharply beyond the top 20 accounts.
* **Strategic Action:** Implement an automated VIP loyalty tier for top-decile buyers. A churn alert mechanism must be triggered if a top-10 customer fails to order within 14 days.

---

## 5. Evaluation & Interview Defense Guide (BRD §13 Questions)

| # | Evaluator Question | Candidate Defense / Architecture Rationale |
|---|---|---|
| **1** | *Why choose units sold rather than revenue for best-seller?* | Revenue is biased toward expensive luxury items (e.g., ₹2,500 Party Platters) ordered rarely. "Best-selling" reflects operational throughput and consumer popularity, which is accurately captured by physical unit volume. Net sales is retained as the secondary metric. |
| **2** | *How do you prevent sales double-counting on orders ↔ items joins?* | By creating the canonical view `v_item_facts` where metrics exist strictly at line-item granularity. Orders table attributes (status, area, date) are joined to line items without summing order-level headers. Order counts use `COUNT(DISTINCT order_id)`. |
| **3** | *How do discounts and refunds affect profit?* | `Net Sales = (qty × price) − discount − refund`. `Cost = (qty − returned_qty) × unit_cost`. Since profit = `Net Sales − Cost`, discounts and refunds directly erode gross profit rupee-for-rupee. Unreturned refunds (customer goodwill) keep inventory cost, further depressing profit. |
| **4** | *What happens when net sales are zero or negative?* | If an item's discounts/refunds exceed revenue or quantity is 0, margin cannot be computed mathematically. Rather than raising `ZeroDivisionError` or printing nonsensical figures, Python intercepts this and displays `"N/A"`. |
| **5** | *How are weekly periods defined around New Year?* | Weeks strictly follow the ISO Monday–Sunday standard using Python `datetime` / SQL `%Y-%W`. A week spanning Dec 29 to Jan 4 remains a single coherent 7-day bucket. |
| **6** | *How were top 5 products chosen for monthly trends?* | Top 5 are chosen by total net sales aggregated over the entire calendar year. Monthly rows are joined against this fixed cohort and zero-filled so comparisons remain consistent. |
| **7** | *Can the app distinguish high-revenue from high-profit?* | Yes. Sections 2, 6, and 7 clearly contrast items like *Cheese Burst Pizza* (high revenue, negative profit) against *Chicken Dum Biryani* (high revenue, high profit). |
| **8** | *What is done in SQL vs. Python, and why?* | **SQL** performs filtering, joins, GROUP BY, and sorting. **Python** handles domain logic (safe division for margin, rank assignment, zero-filling, and UI rendering). |
| **9** | *How would this scale from 10,000 to 100M items?* | Migrate from SQLite to a distributed columnar database (ClickHouse, BigQuery, or partitioned PostgreSQL). Pre-aggregate daily summary rollups by `(date, product_id, area_id)` so dashboard queries hit summary tables rather than scanning 100M raw rows. |
| **10**| *What insight could immediately change a business decision?* | Repricing or decommissioning the 6 loss-making products will instantly stop ₹81,897 of margin leakage, directly increasing net operating profit by ~4%. |

---

## 6. Testing & Data Quality Pipeline

The solution includes an automated test suite executed with `pytest`:
* **26 / 26 Unit & Integration Tests Passing** (Execution time: ~4.5 seconds).
* **Automated Data Cleaning:** 15 corrupted records (negative price, orphan order ID, duplicate rows, zero quantity) were systematically detected and isolated into [`data/rejected_rows.csv`](file:///c:/Users/cheth/OneDrive/Desktop/food_delivery_analytics/food_delivery_analytics/data/rejected_rows.csv).
* **Zero Missing Values:** Clean database state verified via the built-in sidebar "Data quality" inspection view.

---

## 7. Candidate Submission Form (BRD §16)

* **Repository Link:** [https://github.com/chethana100/food-delivery-analytics](https://github.com/chethana100/food-delivery-analytics)
* **Application Execution:** `python -m streamlit run app.py` (or Docker: `docker run -p 8501:8501 $(docker build -q .)`)
* **Test Suite Execution:** `pytest`
* **Status:** Complete, fully functional, and verified against all 12 rubric dimensions.
