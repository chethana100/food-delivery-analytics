-- Food delivery analytics schema (SQLite).
-- Timestamps: ISO-8601 'YYYY-MM-DD HH:MM:SS' in Asia/Kolkata (IST), no offset.

PRAGMA foreign_keys = ON;

DROP VIEW  IF EXISTS v_item_facts;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id   TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL            -- synthetic
);

CREATE TABLE products (
    product_id   INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL UNIQUE,
    brand        TEXT NOT NULL,
    product_type TEXT NOT NULL             -- category, e.g. 'Beverages'
);

CREATE TABLE orders (
    order_id       INTEGER PRIMARY KEY,
    order_datetime TEXT NOT NULL,
    customer_id    TEXT NOT NULL REFERENCES customers(customer_id),
    delivery_area  TEXT,                    -- NULL/blank is reported as 'Unknown'
    order_status   TEXT NOT NULL CHECK (order_status IN ('Delivered', 'Cancelled'))
);

CREATE TABLE order_items (
    order_item_id      INTEGER PRIMARY KEY,
    order_id           INTEGER NOT NULL REFERENCES orders(order_id),
    product_id         INTEGER NOT NULL REFERENCES products(product_id),
    quantity           INTEGER NOT NULL CHECK (quantity > 0),
    unit_selling_price REAL    NOT NULL CHECK (unit_selling_price >= 0),
    discount_amount    REAL    NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    refund_amount      REAL    NOT NULL DEFAULT 0 CHECK (refund_amount >= 0),
    returned_quantity  INTEGER NOT NULL DEFAULT 0 CHECK (returned_quantity >= 0),
    unit_product_cost  REAL    NOT NULL CHECK (unit_product_cost >= 0),
    CHECK (returned_quantity <= quantity)
);

CREATE INDEX ix_orders_datetime ON orders(order_datetime);
CREATE INDEX ix_orders_customer ON orders(customer_id);
CREATE INDEX ix_items_order     ON order_items(order_id);
CREATE INDEX ix_items_product   ON order_items(product_id);

-- One row per VALID (non-cancelled) order line, with every metric defined once.
-- All reports aggregate from this view, so definitions cannot drift between queries.
--   net_sales    = quantity*price - discount - refund
--   units_sold   = quantity - returned_quantity
--   product_cost = (quantity - returned_quantity) * unit_cost   (returned goods are restocked)
--   profit       = net_sales - product_cost                      (computed in analytics layer)
CREATE VIEW v_item_facts AS
SELECT
    oi.order_item_id,
    o.order_id,
    date(o.order_datetime)                              AS order_date,
    date(o.order_datetime,
         '-' || ((CAST(strftime('%w', o.order_datetime) AS INTEGER) + 6) % 7) || ' days')
                                                        AS week_start,      -- Monday
    o.customer_id,
    COALESCE(NULLIF(TRIM(o.delivery_area), ''), 'Unknown') AS delivery_area,
    p.product_id, p.product_name, p.brand, p.product_type,
    oi.quantity,
    oi.quantity - oi.returned_quantity                  AS units_sold,
    oi.quantity * oi.unit_selling_price                 AS gross_sales,
    oi.discount_amount,
    oi.refund_amount,
    ROUND(oi.quantity * oi.unit_selling_price - oi.discount_amount - oi.refund_amount, 2) AS net_sales,
    ROUND((oi.quantity - oi.returned_quantity) * oi.unit_product_cost, 4)       AS product_cost
FROM order_items oi
JOIN orders   o ON o.order_id   = oi.order_id
JOIN products p ON p.product_id = oi.product_id
WHERE o.order_status <> 'Cancelled';
