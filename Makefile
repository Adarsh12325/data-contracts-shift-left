.PHONY: help up down test-producer test-contract dbt-build bench clean

help:
	@echo "Data Contracts Shift-Left Platform - Commands:"
	@echo "  make up             - Provision PostgreSQL container via Docker Compose"
	@echo "  make down           - Stop and remove PostgreSQL container and volumes"
	@echo "  make test-producer  - Run producer test suite and contract tests (pytest)"
	@echo "  make test-contract  - Run Contract CI gatekeeper CLI tool"
	@echo "  make dbt-build      - Build dbt models and run downstream assertions"
	@echo "  make bench          - Execute full 16-change catalog across all 3 layers"
	@echo "  make clean          - Clean temporary caches, compiled artifacts, and results"

up:
	docker compose up -d postgres

down:
	docker compose down -v

test-producer:
	pytest tests/ -v

test-contract:
	python scripts/check_contract.py --schema-file contract.json --payload-file tests/fixtures/sample_payload.json

dbt-build:
	cd analytics && dbt run --profiles-dir . && dbt test --profiles-dir .

bench:
	python scripts/run_catalog.py

clean:
	rm -rf __pycache__ .pytest_cache .coverage analytics/target analytics/dbt_packages
