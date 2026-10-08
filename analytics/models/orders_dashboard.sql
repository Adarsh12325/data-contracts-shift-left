{{ config(materialized='table') }}

/*
  orders_dashboard
  ----------------
  Consumer-facing downstream analytics model aggregating order transactions
  for reporting dashboards.

  Notice: If bad data lands in upstream 'orders', it propagates directly
  into this model prior to downstream dbt test execution.
*/

WITH raw_orders AS (
    SELECT
        id,
        customer_id,
        amount_cents,
        currency,
        status,
        created_at,
        DATE(created_at) AS order_date,
        ROUND((amount_cents / 100.0)::numeric, 2) AS amount_dollars
    FROM {{ source('operational_db', 'orders') }}
)

SELECT
    id,
    customer_id,
    amount_cents,
    amount_dollars,
    currency,
    status,
    order_date,
    created_at
FROM raw_orders
