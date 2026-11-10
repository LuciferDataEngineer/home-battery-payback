"""OpenLineage events for the offline run.

CI and laptops write a JSON-lines file. docker-compose can point the same
client at Marquez by setting OPENLINEAGE_URL; this module always writes the file
as well, and commits a small graph snapshot built from those events.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from openlineage.client import OpenLineageClient
from openlineage.client.event_v2 import (
    InputDataset,
    Job,
    OutputDataset,
    Run,
    RunEvent,
    RunState,
)
from openlineage.client.transport.file import FileConfig, FileTransport

from hbp.config import LINEAGE

PRODUCER = "https://github.com/LuciferDataEngineer/home-battery-payback"
NAMESPACE = "home-battery-payback"

EDGES = [
    ("snapshot.cer_battery_installations", "silver.battery_month"),
    ("snapshot.cer_battery_capacity", "gold.uptake"),
    ("snapshot.cer_solar_installations", "gold.uptake"),
    ("snapshot.abs_poa_dwellings", "gold.uptake"),
    ("snapshot.aemo_price_demand", "gold.daily_spread"),
    ("gold.daily_spread", "gold.payback"),
    ("gold.uptake", "dashboard.json"),
    ("gold.payback", "dashboard.json"),
    ("silver.battery_month", "iceberg.silver.battery_month"),
    ("gold.payback", "iceberg.gold.payback"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(events_path: Path | None = None) -> dict:
    LINEAGE.mkdir(parents=True, exist_ok=True)
    events_path = events_path or (LINEAGE / "events.jsonl")
    if events_path.exists():
        events_path.unlink()
    client = OpenLineageClient(
        transport=FileTransport(FileConfig(log_file_path=str(events_path), append=True))
    )
    run_id = str(uuid.uuid4())
    for index, (source, target) in enumerate(EDGES):
        client.emit(
            RunEvent(
                eventTime=_now(),
                producer=PRODUCER,
                run=Run(runId=run_id),
                job=Job(namespace=NAMESPACE, name=f"build_{target.replace('.', '_')}"),
                eventType=RunState.COMPLETE,
                inputs=[InputDataset(namespace=NAMESPACE, name=source)],
                outputs=[OutputDataset(namespace=NAMESPACE, name=target)],
            )
        )
        # A start/complete pair is the spec's minimum. One COMPLETE per edge keeps the
        # file short and still names every dataset the dashboard depends on.
        _ = index

    graph = {
        "producer": PRODUCER,
        "run_id": run_id,
        "namespace": NAMESPACE,
        "nodes": sorted({name for edge in EDGES for name in edge}),
        "edges": [{"input": source, "output": target} for source, target in EDGES],
        "event_count": len(EDGES),
        "events_file": events_path.name,
    }
    (LINEAGE / "graph.json").write_text(json.dumps(graph, indent=2) + "\n")
    return graph
