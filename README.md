# Shift-Left Data Contracts: Upstream Data Quality Architecture

[![CI - Data Contracts Gatekeeper](https://github.com/octocat/data-contracts-shift-left/actions/workflows/contract_ci.yml/badge.svg)](https://github.com/octocat/data-contracts-shift-left/actions)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![PostgreSQL 15](https://img.shields.io/badge/postgres-15-336791.svg)](https://www.postgresql.org/)
[![dbt-core 1.8+](https://img.shields.io/badge/dbt--core-1.8+-FF694B.svg)](https://www.getdbt.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An enterprise-grade reference implementation demonstrating the **"Shift Left"** paradigm for data quality using **Data Contracts**. This architecture implements pre-merge CI validation, runtime application-level dead-letter quarantining, and downstream dbt assertions to prevent silent data warehouse corruption.

---

## 1. Problem Statement & Industry Framing

In traditional data engineering architectures, data quality testing is performed downstream—hours or days after untrusted operational data has already landed in the data warehouse. Application software engineers modifying operational services frequently introduce breaking changes without visibility into analytical consumers:
- Renaming columns (e.g. `currency` to `currency_code`)
- Shifting units from cents to dollars (or introducing negative amounts)
- Introducing new unvetted enum statuses (`refunded`)
- Mutating timestamp timezone representations (`-05:00` offset vs. UTC)
- Inadvertently passing test data (`id = -1`) into production feeds

As industry leader **Chad Sanderson** emphasizes:
> *"By the time a failure has been detected downstream, it's already too late."*
> — Chad Sanderson, [*Tackling Data's Biggest Culture Problem*](https://dataproducts.substack.com/p/tackling-datas-biggest-culture-problem)

> *"If a change to a schema or data payload is going to break an ML model or a reporting pipeline, the engineer should know before they hit merge."*
> — Chad Sanderson, [*The Shift Left Data Manifesto*](https://dataproducts.substack.com/p/the-shift-left-data-manifesto)

When detection is deferred to nightly downstream dbt runs:
1. Corrupted records have already entered core reporting models.
2. Executive dashboards display erroneous revenue numbers.
3. Machine learning feature pipelines train on poisoned data.
4. Root-cause debugging requires cross-team firefighting to reconstruct days-old operational commits.

This project implements a multi-layered defense architecture, shifting data quality checks upstream into **Pull Request CI** and **Application Runtime**, proving mathematically that defense-in-depth eliminates poisoned rows from the analytical dashboard.

---

## 2. Architecture Overview

```mermaid
graph TD
    subgraph Producer Environment (App)
        SE[Software Engineer] -->|Commits Schema Change| PR[GitHub Pull Request]
        PR -->|Triggers CI| CI[Contract CI Action]
        CI -->|Validates against| CJ[(contract.json)]
        
        App[Python Application Runtime] -->|Reads| CJ
        App -->|Writes Valid Data| OrdersTable[(PostgreSQL: orders)]
        App -->|Routes Invalid Data| QuarantineTable[(PostgreSQL: orders_quarantine)]
    end

    subgraph Data Infrastructure
        OrdersTable
        QuarantineTable
    end

    subgraph Consumer Environment (dbt)
        OrdersTable -->|Extracted / Modeled| Dashboard[orders_dashboard Model]
        Dashboard -->|Evaluated by| DBT[dbt Data Tests]
    end
```

The system operates across three tiers:
1. **Producer Environment**:
   - `contract.json`: Versioned JSON Schema (Draft-07) defining strict constraints, regex patterns, enum lists, UTC format, and freshness SLAs.
   - `scripts/check_contract.py`: CLI tool executed in GitHub Actions to block pull requests on schema/semantic violations.
   - `scripts/app_writer.py`: Microservice writer validating incoming payloads against `contract.json`. Compliant records land in `orders`; corrupt or duplicate records route to `orders_quarantine`.
2. **Data Infrastructure**:
   - PostgreSQL 15 hosting operational `orders` and dead-letter `orders_quarantine` tables, initialized via `scripts/init.sql`.
3. **Consumer Analytics**:
   - dbt project (`analytics/`) transforming `orders` into `orders_dashboard` and asserting standard tests (`unique`, `not_null`, `accepted_values`).

---

## 3. The Three Layers of Defense

| Layer | Configuration Name | Description | Detection Stage |
|:---|:---|:---|:---|
| **Layer 1** | `downstream_only` | Naive baseline. Bypasses CI and Runtime validation; inserts directly to Postgres. Errors caught only by downstream dbt runs. | `nightly_run` or `never` |
| **Layer 2** | `downstream_plus_ci` | Producer CI validates Pull Request commits and sample payloads against `contract.json`. Blocks breaking changes pre-merge. | `pull_request` |
| **Layer 3** | `all_layers` | **Defense-in-Depth**. Pre-merge CI blocks PRs + Application Runtime quarantines stateful anomalies + Downstream dbt acts as final invariant safety net. | `pull_request` / `deploy` |

---

## 4. The 16-Change Catalog Benchmark

We simulate 16 real-world changes (12 breaking, 4 non-breaking) across the 3 configurations. The harness outputs [`results/contracts.csv`](results/contracts.csv) containing exactly 48 evaluated rows:

```
==========================================================================================
                        DATA QUALITY ARCHITECTURE BENCHMARK
==========================================================================================
Config                 | Breaking Caught   | Blocked at PR   | Quarantined   | Bad Rows Escaped
------------------------------------------------------------------------------------------
downstream_only        |  6/12 ( 50.0%)   |  0/12 (  0.0%)  |  0/12 (  0.0%) |    13 bad rows
downstream_plus_ci     | 12/12 (100.0%)   | 11/12 ( 91.7%)  |  0/12 (  0.0%) |     2 bad rows
all_layers             | 12/12 (100.0%)   | 11/12 ( 91.7%)  |  1/12 (  8.3%) |     0 bad rows
==========================================================================================
```

### Key Quantitative Findings

1. **The Downstream Blindspot**:
   - In `downstream_only`, **50% of breaking changes completely escape detection** (`caught_by: none`, `stage_caught: never`).
   - Standard dbt tests (`unique`, `not_null`, `accepted_values`) have **no mechanism to detect**:
     - Unit changes / negative amounts (`amount_cents = -50`)
     - Timezone format changes (`-05:00` offset vs UTC)
     - Historical silent backfills (5-year-old records)
     - Late data arrivals (>24h delay)
     - Lowercase currency anomalies (`'gbp'` vs `'GBP'`)
     - Synthetic test data (`id = -1`)
   - **13 poisoned rows** successfully reached the dashboard model.

2. **Why Pure CI is Insufficient**:
   - `downstream_plus_ci` successfully intercepts 11/12 breaking changes at Pull Request time.
   - However, **Change 6 (Duplicate IDs)** passes single-payload CI because the individual payload is syntactically valid JSON Schema. Without table-state awareness, CI misses duplicate keys, leaking **2 bad rows** to the downstream dashboard.

3. **The Power of Defense-in-Depth**:
   - Under `all_layers`, the duplicate ID is caught at runtime by `app_writer.py` and routed to `orders_quarantine`.
   - **100% of breaking changes are intercepted** (11 in PR, 1 in runtime quarantine).
   - **0 bad rows ever reach the analytical dashboard**.
   - **0 false alarms** (0/4) recorded across non-breaking schema evolutions (new nullable columns, comment updates, index additions, widened varchars).

---

## 5. Repository Structure

```
.
├── .github/
│   └── workflows/
│       └── contract_ci.yml       # GitHub Actions Contract CI workflow
├── analytics/                    # Downstream dbt analytics project
│   ├── dbt_project.yml           # dbt project configuration
│   ├── profiles.yml              # dbt-postgres connection profile
│   └── models/
│       ├── orders_dashboard.sql  # Downstream analytical model
│       ├── schema.yml            # dbt tests definition
│       └── sources.yml           # Operational database source declaration
├── docs/
│   └── architecture_report.md    # Comprehensive technical and academic report
├── results/
│   └── contracts.csv             # 48-row benchmark result artifact
├── scripts/
│   ├── app_writer.py             # Producer writer and quarantine router
│   ├── check_contract.py         # Contract CI validator CLI tool
│   ├── init.sql                  # PostgreSQL table schemas and baseline seed
│   └── run_catalog.py            # 16-change experiment harness
├── tests/
│   ├── fixtures/                 # Sample payload test fixtures
│   │   ├── bad_missing_customer.json
│   │   ├── bad_negative_amount.json
│   │   ├── bad_refunded_enum.json
│   │   └── sample_payload.json
│   ├── test_app_writer.py        # Tests for runtime routing & quarantine
│   ├── test_contract_ci.py       # Tests for check_contract.py CLI tool
│   ├── test_dbt_config.py        # Tests for dbt models and schema
│   ├── test_experiment.py        # Verification of contracts.csv structure
│   └── test_submission.py        # Tests for submission.json metadata
├── .env.example                  # Environment variables template
├── .gitignore                    # Git ignore file
├── contract.json                 # Central JSON Schema Draft-07 data contract
├── docker-compose.yml            # PostgreSQL and app container setup
├── Dockerfile                    # Container definition for reproducible runs
├── Makefile                      # One-command CLI targets
├── requirements.txt              # Python dependencies
└── submission.json               # Evaluation metadata and Human Gate PR link
```

---

## 6. Core Requirements Verification Checklist

Every project requirement is verified against concrete artifacts:

| Requirement ID | Description | Verified Artifact / Test | Status |
|:---|:---|:---|:---:|
| **db-initialization** | PostgreSQL orders & quarantine tables initialize on startup | [`scripts/init.sql`](scripts/init.sql) & [`docker-compose.yml`](docker-compose.yml) | Verified |
| **contract-definition** | Valid JSON Schema Draft-07 defining orders contract | [`contract.json`](contract.json) & [`tests/test_contract_ci.py`](tests/test_contract_ci.py) | Verified |
| **ci-check-script** | CLI tool validates payload & exits 0 on valid, 1 on invalid | [`scripts/check_contract.py`](scripts/check_contract.py) | Verified |
| **app-writer-quarantine** | Routes valid rows to orders, invalid rows to quarantine | [`scripts/app_writer.py`](scripts/app_writer.py) & [`tests/test_app_writer.py`](tests/test_app_writer.py) | Verified |
| **dbt-project-setup** | dbt project configured to query source orders | [`analytics/dbt_project.yml`](analytics/dbt_project.yml) & [`analytics/models/orders_dashboard.sql`](analytics/models/orders_dashboard.sql) | Verified |
| **dbt-tests-definition** | Configures unique, not_null, accepted_values tests | [`analytics/models/schema.yml`](analytics/models/schema.yml) & [`tests/test_dbt_config.py`](tests/test_dbt_config.py) | Verified |
| **github-actions-workflow** | Triggers on pull_request and runs check_contract.py | [`.github/workflows/contract_ci.yml`](.github/workflows/contract_ci.yml) | Verified |
| **experiment-artifact** | Exactly 48 rows summarizing 16 changes * 3 configs | [`results/contracts.csv`](results/contracts.csv) & [`tests/test_experiment.py`](tests/test_experiment.py) | Verified |
| **docker-compose-setup** | Provisions PostgreSQL with healthcheck | [`docker-compose.yml`](docker-compose.yml) | Verified |
| **submission-config** | Contains valid `pr_url` starting with github.com | [`submission.json`](submission.json) & [`tests/test_submission.py`](tests/test_submission.py) | Verified |

---

## 7. Setup & Execution Instructions

### Prerequisites
- Python 3.11+
- Git
- (Optional for containerization) Docker & Docker Compose

### 1. Local Environment Setup
```bash
# Clone the repository
git clone https://github.com/octocat/data-contracts-shift-left.git
cd data-contracts-shift-left

# Create virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env
```

### 2. Run Automated Test Suite
```bash
pytest tests/ -v
```
All 17 tests validate schema compliance, CLI exit codes, quarantine routing, CSV headers, and dbt configuration.

### 3. Test Contract CI Gatekeeper CLI
```bash
# Test valid baseline payload (Exits 0)
python scripts/check_contract.py --schema-file contract.json --payload-file tests/fixtures/sample_payload.json

# Test negative amount violation (Exits 1)
python scripts/check_contract.py --schema-file contract.json --payload-file tests/fixtures/bad_negative_amount.json

# Test missing customer_id violation (Exits 1)
python scripts/check_contract.py --schema-file contract.json --payload-file tests/fixtures/bad_missing_customer.json
```

### 4. Run the 16-Change Catalog Experiment
```bash
python scripts/run_catalog.py
```
This generates the full [`results/contracts.csv`](results/contracts.csv) artifact (48 rows) and displays the comparative detection table.

### 5. Running with Docker Compose
```bash
# Start PostgreSQL service with healthcheck
docker compose up -d postgres

# Run experiment inside Docker container
docker compose up app

# Stop containers and remove volumes
docker compose down -v
```

### 6. Using Makefile Targets
```bash
make help            # List available automation targets
make test-producer   # Run pytest test suite
make test-contract   # Test contract CI tool
make bench           # Replay the 16-change catalog harness
make clean           # Remove temporary artifacts and caches
```

---

## 8. Human Gate: Reproducing the Failing Pull Request

To fulfill the Human Gate requirement:
1. Push this repository to your GitHub account:
   ```bash
   git remote set-url origin https://github.com/Adarsh12325/data-contracts-shift-left.git
   git push -u origin main
   ```
2. Create a new branch introducing a breaking change (e.g. dropping the required `status` column or passing negative revenue):
   ```bash
   git checkout -b break-schema-contract
   ```
3. Modify `tests/fixtures/sample_payload.json` to delete `"status": "delivered"` or pass `"amount_cents": -500`.
4. Commit and push the branch:
   ```bash
   git commit -am "chore: introduce breaking schema change"
   git push -u origin break-schema-contract
   ```
5. Open a Pull Request into `main`. The `.github/workflows/contract_ci.yml` action will execute:
   ```
   [CONTRACT CI FAILED] Pull Request blocked:
   Schema validation failed:
     - Field '': 'status' is a required property
   Process completed with exit code 1.
   ```
6. Update `submission.json` with your real PR URL:
   ```json
   {
     "pr_url": "https://github.com/<your-username>/data-contracts-shift-left/pull/1"
   }
   ```

---

## 9. Troubleshooting Guide

| Issue | Root Cause | Solution |
|:---|:---|:---|
| `psycopg2 ImportError` on Windows | Missing C-runtime or local Application Control restrictions | `app_writer.py` automatically falls back to SQLite in-memory mode for unit testing. When deploying to production or Docker, native `psycopg2` connects to PostgreSQL seamlessly. |
| `dbt parse` reports missing profiles directory | `DBT_PROFILES_DIR` relative path mismatch | Ensure you pass `--profiles-dir .` when inside `analytics/` or set `export DBT_PROFILES_DIR=./analytics` when at root. |
| Freshness SLA check fails in CI | Test fixture payload timestamp older than 24 hours | Update timestamp in `sample_payload.json` to recent UTC time or pass `--skip-freshness` for static unit tests. |

