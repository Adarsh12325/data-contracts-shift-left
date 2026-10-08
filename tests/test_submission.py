"""
Verification Tests for submission.json Metadata and Human Gate Reference
"""

import os
import json
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SUBMISSION_FILE = os.path.join(REPO_ROOT, "submission.json")


def test_submission_json_exists():
    assert os.path.exists(SUBMISSION_FILE), "submission.json must exist at root"


def test_submission_json_pr_url_validity():
    with open(SUBMISSION_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "pr_url" in data, "submission.json must contain 'pr_url' key"
    pr_url = data["pr_url"]
    assert isinstance(pr_url, str), "pr_url must be a string"
    assert pr_url.startswith("https://github.com/"), f"pr_url must start with https://github.com/, got: {pr_url}"
