"""
Unit and Integration Tests for Application Writer and Quarantine Mechanism (app_writer.py)
"""

import os
import sys
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from app_writer import AppWriter


@pytest.fixture
def clean_writer(tmp_path):
    """Provides an isolated AppWriter instance with SQLite backing."""
    db_file = str(tmp_path / "test_orders.db")
    writer = AppWriter(
        contract_path=os.path.join(REPO_ROOT, "contract.json"),
        use_sqlite_fallback=True,
        sqlite_path=db_file
    )
    writer.reset_tables()
    yield writer
    writer.close()


def test_write_valid_record(clean_writer):
    """Verify that a valid record routes to 'orders'."""
    valid_payload = {
        "id": 9991,
        "customer_id": 100,
        "amount_cents": 3500,
        "currency": "USD",
        "status": "delivered",
        "created_at": "2026-10-07T12:00:00Z"
    }

    result = clean_writer.write_record(valid_payload)
    assert result["status"] == "written_to_orders"
    assert result["table"] == "orders"
    assert clean_writer.get_orders_count() == 1
    assert clean_writer.get_quarantine_count() == 0


def test_write_invalid_record_quarantines(clean_writer):
    """Verify that an invalid record (bad enum status) routes to 'orders_quarantine'."""
    invalid_payload = {
        "id": 9992,
        "customer_id": 101,
        "amount_cents": 5500,
        "currency": "USD",
        "status": "refunded",  # Not in enum
        "created_at": "2026-10-07T12:00:00Z"
    }

    result = clean_writer.write_record(invalid_payload)
    assert result["status"] == "quarantined"
    assert result["table"] == "orders_quarantine"
    assert "status" in result["error"]
    assert clean_writer.get_orders_count() == 0
    assert clean_writer.get_quarantine_count() == 1


def test_verification_requirement_one_each(clean_writer):
    """
    Verification test required by Core Requirement 4:
    Insert 1 valid record and 1 invalid record.
    Verify orders table contains exactly 1 row and orders_quarantine contains exactly 1 row.
    """
    clean_writer.reset_tables()

    valid_record = {
        "id": 5001,
        "customer_id": 200,
        "amount_cents": 1200,
        "currency": "EUR",
        "status": "pending",
        "created_at": "2026-10-07T12:00:00Z"
    }
    invalid_record = {
        "id": 5002,
        "customer_id": 201,
        "amount_cents": -99,  # Negative amount
        "currency": "EUR",
        "status": "pending",
        "created_at": "2026-10-07T12:00:00Z"
    }

    res_valid = clean_writer.write_record(valid_record)
    res_invalid = clean_writer.write_record(invalid_record)

    assert res_valid["table"] == "orders"
    assert res_invalid["table"] == "orders_quarantine"

    assert clean_writer.get_orders_count() == 1, "orders table must contain exactly 1 row"
    assert clean_writer.get_quarantine_count() == 1, "orders_quarantine must contain exactly 1 row"


def test_duplicate_id_quarantining(clean_writer):
    """Verify duplicate IDs are caught at runtime and quarantined."""
    clean_writer.reset_tables()
    payload = {
        "id": 7001,
        "customer_id": 300,
        "amount_cents": 4000,
        "currency": "USD",
        "status": "shipped",
        "created_at": "2026-10-07T12:00:00Z"
    }
    clean_writer.write_record(payload)
    # Attempt inserting identical ID
    res2 = clean_writer.write_record(payload)
    assert res2["status"] == "quarantined"
    assert "already exists" in res2["error"]
    assert clean_writer.get_orders_count() == 1
    assert clean_writer.get_quarantine_count() == 1
