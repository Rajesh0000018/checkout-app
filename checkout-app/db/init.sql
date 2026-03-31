-- ─────────────────────────────────────────────────────────────────────────────
-- CheckoutOS — Postgres initialisation script
-- Run once on a fresh database, or mount as /docker-entrypoint-initdb.d/init.sql
-- ─────────────────────────────────────────────────────────────────────────────

-- Create the audit table that the checkout service writes to on every
-- successful checkout. The checkout service also runs this via
-- CREATE TABLE IF NOT EXISTS at startup, so this file is belt-and-braces.

CREATE TABLE IF NOT EXISTS checkout_audit (
    id          SERIAL          PRIMARY KEY,
    request_id  TEXT            NOT NULL,
    customer_id TEXT,
    sku         TEXT            NOT NULL,
    quantity    INT             NOT NULL,
    total_price NUMERIC(10, 2)  NOT NULL,
    created_at  TIMESTAMP       DEFAULT NOW()
);

-- Index for fast lookup by request_id (correlation / support queries)
CREATE INDEX IF NOT EXISTS idx_checkout_audit_request_id
    ON checkout_audit (request_id);

-- Index for customer history queries
CREATE INDEX IF NOT EXISTS idx_checkout_audit_customer_id
    ON checkout_audit (customer_id);

-- Index for time-range queries (e.g. "orders in the last hour")
CREATE INDEX IF NOT EXISTS idx_checkout_audit_created_at
    ON checkout_audit (created_at DESC);
