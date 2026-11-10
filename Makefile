.PHONY: help install lint test ingest pipeline export dashboard flink-test ci-snapshot

PYTHON ?= python3

help:
	@echo "install lint test ingest pipeline export dashboard flink-test"

install:
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	ruff check src tests

test:
	pytest -m "not flink and not browser"

ingest:
	$(PYTHON) -m hbp.ingest

pipeline:
	$(PYTHON) -m hbp.pipeline --from-snapshot

export: pipeline

dashboard: pipeline

flink-test:
	JAVA_HOME=$${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64} PYTHONPATH=src pytest -m flink

ci-snapshot: lint test pipeline

compose-up:
	docker compose up -d minio iceberg-rest trino

compose-smoke: compose-up
	sh scripts/trino_smoke.sh
