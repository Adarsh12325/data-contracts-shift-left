"""
Verification Tests for dbt Configuration, Models, and Test Schemas
"""

import os
import yaml
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ANALYTICS_DIR = os.path.join(REPO_ROOT, "analytics")
DBT_PROJECT_FILE = os.path.join(ANALYTICS_DIR, "dbt_project.yml")
PROFILES_FILE = os.path.join(ANALYTICS_DIR, "profiles.yml")
DASHBOARD_SQL = os.path.join(ANALYTICS_DIR, "models", "orders_dashboard.sql")
SCHEMA_YML = os.path.join(ANALYTICS_DIR, "models", "schema.yml")
SOURCES_YML = os.path.join(ANALYTICS_DIR, "models", "sources.yml")


def test_dbt_project_structure():
    assert os.path.exists(DBT_PROJECT_FILE), "dbt_project.yml must exist"
    assert os.path.exists(PROFILES_FILE), "profiles.yml must exist"
    assert os.path.exists(DASHBOARD_SQL), "orders_dashboard.sql must exist"
    assert os.path.exists(SCHEMA_YML), "schema.yml must exist"
    assert os.path.exists(SOURCES_YML), "sources.yml must exist"


def test_orders_dashboard_sql_source_reference():
    with open(DASHBOARD_SQL, "r", encoding="utf-8") as f:
        content = f.read()
    assert "source('operational_db', 'orders')" in content or "orders" in content
    assert "SELECT" in content.upper()


def test_schema_yml_tests_definition():
    with open(SCHEMA_YML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    models = data.get("models", [])
    dashboard_model = next((m for m in models if m.get("name") == "orders_dashboard"), None)
    assert dashboard_model is not None, "orders_dashboard model must be defined in schema.yml"

    columns = {col["name"]: col for col in dashboard_model.get("columns", [])}

    # 1. id column tests: not_null and unique
    assert "id" in columns, "id column must be defined"
    id_tests = columns["id"].get("tests", [])
    assert "unique" in id_tests, "id must have unique test"
    assert "not_null" in id_tests, "id must have not_null test"

    # 2. customer_id column test: not_null
    assert "customer_id" in columns, "customer_id column must be defined"
    cust_tests = columns["customer_id"].get("tests", [])
    assert "not_null" in cust_tests, "customer_id must have not_null test"

    # 3. status column test: accepted_values
    assert "status" in columns, "status column must be defined"
    status_tests = columns["status"].get("tests", [])
    accepted_values_test = next(
        (t for t in status_tests if isinstance(t, dict) and "accepted_values" in t), None
    )
    assert accepted_values_test is not None, "status must have accepted_values test"
    values = accepted_values_test["accepted_values"]["values"]
    assert set(values) == {"pending", "shipped", "delivered", "cancelled"}
