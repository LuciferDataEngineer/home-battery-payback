"""Offline pipeline: snapshot checks, marts, lakehouse, lineage, dashboard JSON.

`--light` is what the Kubernetes job runs. It still computes the gold numbers
from the snapshot. It does not open the Iceberg catalog or Dagster.
"""

from __future__ import annotations

import argparse

from hbp.analytics import build_all
from hbp.config import SITE_DATA
from hbp.export import build_document


def _write_dashboard(document: dict) -> None:
    import json

    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "dashboard.json").write_text(json.dumps(document, indent=2) + "\n")


def run_light() -> dict:
    bundle = build_all()
    document = build_document(bundle)
    _write_dashboard(document)
    sa = next(row for row in document["regions"] if row["region"] == "SA1")
    tas = next(row for row in document["regions"] if row["region"] == "TAS1")
    print(f"GOLD_BATTERIES={document['national']['batteries']}")
    print(f"GOLD_SA_AVG_SPREAD={sa['avg_spread']}")
    print(f"GOLD_TAS_AVG_SPREAD={tas['avg_spread']}")
    print(f"GOLD_SA_PAYBACK_YEARS={document['callouts']['sa_years']}")
    return document


def run_full() -> dict:
    from hbp.benchmark import run as run_benchmark
    from hbp.dagster_defs import materialize_all
    from hbp.iceberg_store import publish
    from hbp.lineage_emit import emit

    document = materialize_all()
    bundle = build_all()
    report = publish(bundle)
    graph = emit()
    timings = run_benchmark()
    print(f"ICEBERG_RESTORED={report['correction_drill']['restored_installs']}")
    print(f"LINEAGE_EDGES={graph['event_count']}")
    print(f"BENCH_DUCKDB_MS={timings['duckdb_day_agg_ms']}")
    _ = document
    return build_document(bundle)


def main() -> None:
    parser = argparse.ArgumentParser(description="Home battery payback pipeline")
    parser.add_argument("--from-snapshot", action="store_true")
    parser.add_argument("--light", action="store_true")
    args = parser.parse_args()
    if not args.from_snapshot and not args.light:
        parser.error("pass --from-snapshot (CI and laptops) or --light (Kubernetes)")
    if args.light:
        run_light()
    else:
        run_full()


if __name__ == "__main__":
    main()
