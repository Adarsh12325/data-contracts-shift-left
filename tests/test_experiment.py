"""
Verification Tests for Experiment Results Artifact (results/contracts.csv)
"""

import os
import csv
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULTS_CSV = os.path.join(REPO_ROOT, "results", "contracts.csv")

EXPECTED_HEADERS = [
    "change_id",
    "change_type",
    "breaking",
    "config",
    "caught_by",
    "stage_caught",
    "bad_rows_in_dashboard",
    "false_alarm"
]

EXPECTED_CONFIGS = ["downstream_only", "downstream_plus_ci", "all_layers"]


def test_results_csv_exists():
    assert os.path.exists(RESULTS_CSV), f"results/contracts.csv must exist at {RESULTS_CSV}"


def test_results_csv_headers():
    with open(RESULTS_CSV, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
    assert headers == EXPECTED_HEADERS, f"Headers mismatch. Expected: {EXPECTED_HEADERS}, Got: {headers}"


def test_results_csv_row_counts_and_structure():
    with open(RESULTS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # 1. Exactly 48 rows
    assert len(rows) == 48, f"Expected exactly 48 rows, got {len(rows)}"

    # 2. Change IDs range from 1 to 16
    change_ids = set(int(r["change_id"]) for r in rows)
    assert change_ids == set(range(1, 17)), f"Change IDs must be exactly 1..16, got: {change_ids}"

    # 3. Exactly 16 rows per configuration
    for cfg in EXPECTED_CONFIGS:
        cfg_rows = [r for r in rows if r["config"] == cfg]
        assert len(cfg_rows) == 16, f"Config '{cfg}' must have exactly 16 rows, got {len(cfg_rows)}"

    # 4. Zero false alarms on non-breaking changes
    non_breaking_rows = [r for r in rows if r["breaking"] == "False"]
    assert len(non_breaking_rows) == 12  # 4 non-breaking * 3 configs = 12
    for r in non_breaking_rows:
        assert r["false_alarm"] == "False", f"False alarm flagged on non-breaking change: {r}"
        assert int(r["bad_rows_in_dashboard"]) == 0

    # 5. In all_layers, zero bad rows reach the dashboard
    all_layers_rows = [r for r in rows if r["config"] == "all_layers"]
    for r in all_layers_rows:
        assert int(r["bad_rows_in_dashboard"]) == 0, f"Bad rows leaked in all_layers: {r}"
