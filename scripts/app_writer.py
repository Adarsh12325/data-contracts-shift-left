#!/usr/bin/env python3
"""
Application Runtime Writer & Quarantine Router (app_writer.py)
--------------------------------------------------------------
Simulates the producer microservice runtime. Evaluates each incoming data
payload against the central contract.json.

Routing Logic:
- Valid Payloads: Cleanly written to operational 'orders' table.
- Invalid Payloads: Routed to 'orders_quarantine' table with full payload JSONB
  and failure rationale, keeping the primary table free of poisoned rows.
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone
import dateutil.parser

# Support .env loading
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Try psycopg2 for PostgreSQL, with automatic SQLite fallback for isolated unit testing
try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

import sqlite3

# Import validator from check_contract
try:
    from check_contract import validate_payload_dict
except ImportError:
    try:
        from scripts.check_contract import validate_payload_dict
    except ImportError:
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from check_contract import validate_payload_dict


class AppWriter:
    """
    Simulates operational application data writer with contract enforcement.
    """

    def __init__(self, contract_path: str = None, use_sqlite_fallback: bool = False, sqlite_path: str = None):
        self.contract_path = contract_path or os.getenv("CONTRACT_PATH", "contract.json")
        self.contract = self._load_contract()
        self.use_sqlite = use_sqlite_fallback
        self.sqlite_path = sqlite_path or ":memory:"

        # DB Connection configuration
        self.pg_host = os.getenv("POSTGRES_HOST", "localhost")
        self.pg_port = os.getenv("POSTGRES_PORT", "5432")
        self.pg_db = os.getenv("POSTGRES_DB", "orders_db")
        self.pg_user = os.getenv("POSTGRES_USER", "postgres_user")
        self.pg_password = os.getenv("POSTGRES_PASSWORD", "postgres_password")

        self.conn = None
        self._init_connection()

    def _load_contract(self) -> dict:
        if not os.path.exists(self.contract_path):
            # Attempt finding in root if called from scripts/
            alt_path = os.path.join(os.path.dirname(__file__), "..", self.contract_path)
            if os.path.exists(alt_path):
                self.contract_path = alt_path
            else:
                raise FileNotFoundError(f"Contract file not found at {self.contract_path}")

        with open(self.contract_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _init_connection(self):
        """Initializes PostgreSQL connection or falls back gracefully to SQLite."""
        if not self.use_sqlite and PSYCOPG2_AVAILABLE:
            try:
                self.conn = psycopg2.connect(
                    host=self.pg_host,
                    port=self.pg_port,
                    dbname=self.pg_db,
                    user=self.pg_user,
                    password=self.pg_password,
                    connect_timeout=2
                )
                self.conn.autocommit = True
                self._ensure_pg_tables()
                return
            except Exception as e:
                # If Postgres is not reachable locally (e.g. running outside Docker), use SQLite fallback
                self.use_sqlite = True

        # Fallback to SQLite
        self.conn = sqlite3.connect(self.sqlite_path)
        self._ensure_sqlite_tables()

    def _ensure_pg_tables(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY,
                    customer_id INTEGER NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    currency VARCHAR(10) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orders_quarantine (
                    quarantine_id SERIAL PRIMARY KEY,
                    raw_payload JSONB NOT NULL,
                    error_reason TEXT NOT NULL,
                    quarantined_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC'),
                    source_service VARCHAR(100) DEFAULT 'producer_order_service'
                );
            """)

    def _ensure_sqlite_tables(self):
        cur = self.conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER,
                amount_cents INTEGER,
                currency TEXT,
                status TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS orders_quarantine (
                quarantine_id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_payload TEXT NOT NULL,
                error_reason TEXT NOT NULL,
                quarantined_at TEXT,
                source_service TEXT DEFAULT 'producer_order_service'
            );
        """)
        self.conn.commit()

    def reset_tables(self):
        """Truncates both orders and quarantine tables."""
        if self.use_sqlite:
            cur = self.conn.cursor()
            cur.execute("DELETE FROM orders;")
            cur.execute("DELETE FROM orders_quarantine;")
            self.conn.commit()
        else:
            with self.conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE orders, orders_quarantine RESTART IDENTITY;")

    def _is_duplicate_id(self, order_id: int) -> bool:
        """Checks if order_id already exists in orders table."""
        if self.use_sqlite:
            cur = self.conn.cursor()
            cur.execute("SELECT 1 FROM orders WHERE id = ?", (order_id,))
            return cur.fetchone() is not None
        else:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 FROM orders WHERE id = %s", (order_id,))
                return cur.fetchone() is not None

    def write_record(self, payload: dict, enforce_contract: bool = True) -> dict:
        """
        Processes an incoming record.
        If enforce_contract is True, validates against contract.json and duplicate key state.
        Routes to orders if valid, or orders_quarantine if invalid.
        """
        if enforce_contract:
            is_valid, reason = validate_payload_dict(self.contract, payload)
            if not is_valid:
                return self._quarantine(payload, reason)

            # Check primary key duplication
            if "id" in payload and self._is_duplicate_id(payload["id"]):
                return self._quarantine(
                    payload,
                    f"Integrity violation: Order id={payload['id']} already exists in orders table."
                )

        return self._insert_order(payload)

    def write_raw_record(self, payload: dict) -> dict:
        """
        Bypasses contract and writes raw record directly to orders (or attempts to).
        Used by the downstream_only configuration.
        """
        try:
            return self._insert_order(payload)
        except Exception as e:
            return {"status": "db_error", "table": "none", "error": str(e)}

    def _insert_order(self, payload: dict) -> dict:
        """Inserts record directly into the orders table."""
        # Handle parsed timestamp format
        created_at_val = payload.get("created_at")
        if created_at_val:
            try:
                # Normalize for storage
                dt = dateutil.parser.isoparse(str(created_at_val))
                created_at_val = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

        if self.use_sqlite:
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT INTO orders (id, customer_id, amount_cents, currency, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("id"),
                    payload.get("customer_id"),
                    payload.get("amount_cents"),
                    payload.get("currency"),
                    payload.get("status"),
                    created_at_val
                )
            )
            self.conn.commit()
        else:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO orders (id, customer_id, amount_cents, currency, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        payload.get("id"),
                        payload.get("customer_id"),
                        payload.get("amount_cents"),
                        payload.get("currency"),
                        payload.get("status"),
                        created_at_val
                    )
                )

        return {"status": "written_to_orders", "table": "orders", "id": payload.get("id")}

    def _quarantine(self, payload: dict, error_reason: str) -> dict:
        """Routes invalid payload to orders_quarantine."""
        payload_json = json.dumps(payload)
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        if self.use_sqlite:
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT INTO orders_quarantine (raw_payload, error_reason, quarantined_at, source_service)
                VALUES (?, ?, ?, ?)
                """,
                (payload_json, error_reason, now_ts, "producer_order_service")
            )
            self.conn.commit()
        else:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO orders_quarantine (raw_payload, error_reason, quarantined_at, source_service)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (payload_json, error_reason, now_ts, "producer_order_service")
                )

        return {"status": "quarantined", "table": "orders_quarantine", "error": error_reason}

    def get_orders_count(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM orders;")
        count = cur.fetchone()[0]
        if not self.use_sqlite:
            cur.close()
        return count

    def get_quarantine_count(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM orders_quarantine;")
        count = cur.fetchone()[0]
        if not self.use_sqlite:
            cur.close()
        return count

    def close(self):
        if self.conn:
            self.conn.close()


def main():
    parser = argparse.ArgumentParser(description="Application Runtime Writer with Contract Validation")
    parser.add_argument("--payload", help="JSON string of payload to write")
    parser.add_argument("--payload-file", help="Path to JSON payload file to write")
    parser.add_argument("--raw", action="store_true", help="Bypass contract validation (downstream_only mode)")
    parser.add_argument("--reset", action="store_true", help="Reset both orders and quarantine tables")
    parser.add_argument("--sqlite", action="store_true", help="Force SQLite in-memory mode")
    args = parser.parse_args()

    writer = AppWriter(use_sqlite_fallback=args.sqlite)

    if args.reset:
        writer.reset_tables()
        print("Orders and orders_quarantine tables reset successfully.")
        return

    payload_data = None
    if args.payload:
        payload_data = json.loads(args.payload)
    elif args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as f:
            payload_data = json.load(f)

    if payload_data:
        if args.raw:
            result = writer.write_raw_record(payload_data)
        else:
            result = writer.write_record(payload_data)
        print(f"Result: {json.dumps(result, indent=2)}")
        print(f"Orders count: {writer.get_orders_count()}, Quarantine count: {writer.get_quarantine_count()}")
    else:
        print("No payload provided. Use --payload or --payload-file.")


if __name__ == "__main__":
    main()
