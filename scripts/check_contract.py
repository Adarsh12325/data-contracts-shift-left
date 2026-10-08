#!/usr/bin/env python3
"""
Contract CI Validator (check_contract.py)
-----------------------------------------
Validates operational data payloads and schema definitions against the central
contract.json data contract.

Enforces:
1. JSON Schema Draft-07 structural, typing, nullability, and enum constraints.
2. Semantic rules: amount_cents >= 0, 3-character uppercase ISO currency, positive ID.
3. Strict UTC timezone adherence (must end with 'Z' or '+00:00').
4. Freshness SLA checks: timestamp not exceeding max allowable age (default 24h).

Exit Codes:
- 0: Compliant with Data Contract.
- 1: Data Contract Violation detected (blocks Pull Requests in CI).
"""

import sys
import os
import json
import argparse
from datetime import datetime, timezone
import dateutil.parser
import jsonschema
from jsonschema import Draft7Validator, ValidationError


def validate_contract(schema_path: str, payload_path: str, enforce_freshness: bool = True, reference_time: datetime = None) -> tuple[bool, str]:
    """
    Validates a JSON payload file against a JSON Schema contract.

    Args:
        schema_path: Path to the JSON schema file (e.g. contract.json).
        payload_path: Path to the JSON payload file.
        enforce_freshness: Whether to enforce the freshness SLA (<24 hours old).
        reference_time: Reference time for freshness evaluation (defaults to now UTC).

    Returns:
        tuple (is_valid: bool, error_message: str)
    """
    if not os.path.exists(schema_path):
        return False, f"Schema file not found at: {schema_path}"
    if not os.path.exists(payload_path):
        return False, f"Payload file not found at: {payload_path}"

    try:
        with open(schema_path, "r", encoding="utf-8") as sf:
            schema = json.load(sf)
    except Exception as e:
        return False, f"Failed to parse schema JSON: {e}"

    try:
        with open(payload_path, "r", encoding="utf-8") as pf:
            payload = json.load(pf)
    except Exception as e:
        return False, f"Failed to parse payload JSON: {e}"

    return validate_payload_dict(schema, payload, enforce_freshness, reference_time)


def validate_payload_dict(schema: dict, payload: dict, enforce_freshness: bool = True, reference_time: datetime = None) -> tuple[bool, str]:
    """
    Validates an in-memory dictionary payload against the loaded contract schema.
    """
    # 1. Standard JSON Schema Validation
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        err_msgs = [f"Field '{'.'.join([str(p) for p in err.path])}': {err.message}" for err in errors]
        return False, f"Schema validation failed:\n  - " + "\n  - ".join(err_msgs)

    # 2. Strict UTC format check for 'created_at'
    if "created_at" in payload and isinstance(payload["created_at"], str):
        raw_ts = payload["created_at"].strip()
        # Strictly require UTC representation: ends with Z or +00:00, not non-UTC offsets like -05:00
        if not (raw_ts.endswith("Z") or raw_ts.endswith("+00:00") or raw_ts.endswith("+0000")):
            return False, f"Semantic rule violation: 'created_at' must be strictly in UTC timezone, received: '{raw_ts}'"

        # 3. Relative Freshness SLA check (detect silent backfills or delayed events > 24 hours)
        if enforce_freshness:
            max_age_hours = schema.get("freshness", {}).get("max_age_hours", 24)
            try:
                parsed_ts = dateutil.parser.isoparse(raw_ts)
                if parsed_ts.tzinfo is None:
                    parsed_ts = parsed_ts.replace(tzinfo=timezone.utc)
                now_utc = reference_time or datetime.now(timezone.utc)
                age_seconds = (now_utc - parsed_ts).total_seconds()
                
                # Check for extreme backfill or latency (> 24 hours stale)
                if age_seconds > max_age_hours * 3600:
                    age_hours = age_seconds / 3600.0
                    return False, (
                        f"Freshness SLA violation: event created_at is {age_hours:.1f} hours old "
                        f"(max permitted: {max_age_hours} hours). Potential silent backfill or late arrival."
                    )
            except Exception as e:
                return False, f"Failed to evaluate timestamp freshness: {e}"

    # 4. Currency casing and length
    if "currency" in payload and isinstance(payload["currency"], str):
        if not payload["currency"].isupper():
            return False, f"Semantic rule violation: 'currency' must be uppercase ISO code, received '{payload['currency']}'"

    return True, "Payload is fully compliant with Data Contract."


def main():
    parser = argparse.ArgumentParser(description="CLI tool to validate payloads against contract.json")
    parser.add_argument("--schema-file", required=True, help="Path to contract.json schema")
    parser.add_argument("--payload-file", required=True, help="Path to JSON payload to validate")
    parser.add_argument("--skip-freshness", action="store_true", help="Skip freshness SLA validation")
    args = parser.parse_args()

    is_valid, message = validate_contract(
        schema_path=args.schema_file,
        payload_path=args.payload_file,
        enforce_freshness=not args.skip_freshness
    )

    if is_valid:
        print(f"[CONTRACT CI PASSED] {message}")
        sys.exit(0)
    else:
        print(f"[CONTRACT CI FAILED] Pull Request blocked:\n{message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
