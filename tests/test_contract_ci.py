"""
Unit and Integration Tests for Contract CI Gatekeeper (check_contract.py)
"""

import os
import json
import subprocess
import pytest
import jsonschema

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONTRACT_PATH = os.path.join(REPO_ROOT, "contract.json")
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
FIXTURES_DIR = os.path.join(REPO_ROOT, "tests", "fixtures")


def test_contract_schema_validity():
    """Verify contract.json is syntactically valid JSON Schema Draft-07."""
    assert os.path.exists(CONTRACT_PATH), "contract.json must exist at root"
    with open(CONTRACT_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)

    # Validates against Draft-07 meta-schema
    jsonschema.Draft7Validator.check_schema(schema)
    assert schema.get("type") == "object"
    assert "required" in schema
    assert set(["id", "customer_id", "amount_cents", "currency", "status", "created_at"]).issubset(
        set(schema["required"])
    )


def test_cli_valid_payload():
    """Verify check_contract.py returns exit code 0 for valid payload."""
    valid_payload = os.path.join(FIXTURES_DIR, "sample_payload.json")
    cmd = [
        "python",
        os.path.join(SCRIPTS_DIR, "check_contract.py"),
        "--schema-file", CONTRACT_PATH,
        "--payload-file", valid_payload,
        "--skip-freshness"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Expected 0, got {res.returncode}. Output:\n{res.stdout}\n{res.stderr}"
    assert "CONTRACT CI PASSED" in res.stdout


def test_cli_negative_amount_fails():
    """Verify check_contract.py returns exit code 1 for negative amount_cents."""
    bad_payload = os.path.join(FIXTURES_DIR, "bad_negative_amount.json")
    cmd = [
        "python",
        os.path.join(SCRIPTS_DIR, "check_contract.py"),
        "--schema-file", CONTRACT_PATH,
        "--payload-file", bad_payload,
        "--skip-freshness"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 1, f"Expected 1, got {res.returncode}. Output:\n{res.stdout}"
    assert "CONTRACT CI FAILED" in res.stderr


def test_cli_missing_customer_id_fails():
    """Verify check_contract.py returns exit code 1 when customer_id is missing."""
    bad_payload = os.path.join(FIXTURES_DIR, "bad_missing_customer.json")
    cmd = [
        "python",
        os.path.join(SCRIPTS_DIR, "check_contract.py"),
        "--schema-file", CONTRACT_PATH,
        "--payload-file", bad_payload,
        "--skip-freshness"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 1, f"Expected 1, got {res.returncode}. Output:\n{res.stdout}"
    assert "CONTRACT CI FAILED" in res.stderr


def test_cli_invalid_enum_status_fails():
    """Verify check_contract.py returns exit code 1 for unapproved status enum."""
    bad_payload = os.path.join(FIXTURES_DIR, "bad_refunded_enum.json")
    cmd = [
        "python",
        os.path.join(SCRIPTS_DIR, "check_contract.py"),
        "--schema-file", CONTRACT_PATH,
        "--payload-file", bad_payload,
        "--skip-freshness"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 1, f"Expected 1, got {res.returncode}. Output:\n{res.stdout}"
    assert "CONTRACT CI FAILED" in res.stderr
