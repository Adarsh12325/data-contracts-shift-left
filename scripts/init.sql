-- ==============================================================================
-- Schema Initialization for Data Contracts Shift-Left Platform
-- ==============================================================================

-- Drop tables if needed during fresh container provisioning
-- DROP TABLE IF EXISTS orders CASCADE;
-- DROP TABLE IF EXISTS orders_quarantine CASCADE;

-- 1. Main Operational Orders Table (Producer storage)
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    amount_cents INTEGER NOT NULL,
    currency VARCHAR(10) NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

-- 2. Dead-Letter / Quarantine Table for Rejected Payloads
CREATE TABLE IF NOT EXISTS orders_quarantine (
    quarantine_id SERIAL PRIMARY KEY,
    raw_payload JSONB NOT NULL,
    error_reason TEXT NOT NULL,
    quarantined_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC'),
    source_service VARCHAR(100) DEFAULT 'producer_order_service'
);

-- Indices for performance
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);

-- Initial baseline valid records
INSERT INTO orders (id, customer_id, amount_cents, currency, status, created_at)
VALUES
    (1001, 501, 1999, 'USD', 'delivered', (NOW() - INTERVAL '3 hours') AT TIME ZONE 'UTC'),
    (1002, 502, 4500, 'USD', 'shipped', (NOW() - INTERVAL '2 hours') AT TIME ZONE 'UTC'),
    (1003, 503, 12000, 'EUR', 'pending', (NOW() - INTERVAL '1 hour') AT TIME ZONE 'UTC'),
    (1004, 504, 850, 'USD', 'delivered', (NOW() - INTERVAL '30 minutes') AT TIME ZONE 'UTC')
ON CONFLICT (id) DO NOTHING;
