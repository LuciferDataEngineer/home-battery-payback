.PHONY: help install lint test ingest pipeline export dashboard ci-snapshot flink-smoke kind-smoke compose-smoke

PYTHON ?= python3
UV ?= uv

help:
	@echo "Targets: install lint test ingest pipeline export dashboard ci-snapshot"

install:
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	ruff check src tests

test:
	pytest

ingest:
	$(PYTHON) -m hbp.ingest

pipeline:
	$(PYTHON) -m hbp.pipeline --from-snapshot

export:
	$(PYTHON) -m hbp.export

dashboard: export
	@echo "Dashboard JSON written to site/data/"

ci-snapshot: pipeline export test

flink-smoke:
	$(PYTHON) -m hbp.flink_job --source file --input data/snapshot/prices

kind-smoke:
	@echo "kind smoke is executed by .github/workflows/ci.yml"

compose-smoke:
	docker compose -f docker-compose.yml up -d minio iceberg-rest trino
	docker compose -f docker-compose.yml ps
