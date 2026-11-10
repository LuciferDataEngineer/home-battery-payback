"""Local Iceberg catalog: bronze, silver, gold, schema change, time travel, row deletes.

PyIceberg 0.12 accepts table property write.delete.mode=merge-on-read and then
falls back to copy-on-write, because equality-delete writes are not implemented
yet (https://github.com/apache/iceberg/issues/6568). The delete still removes the
row and creates a new snapshot. Trino in docker-compose honours merge-on-read
for real; see scripts/trino_smoke.sh and BENCHMARK.md.

The revision drilled here adds one installation and then puts the original
Clean Energy Regulator count back. The wrong count exists only in an intermediate
snapshot. Dashboard numbers are computed from the snapshot files, not from that drill.
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pyarrow as pa
from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.expressions import And, EqualTo
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import IdentityTransform, MonthTransform
from pyiceberg.types import DateType, DoubleType, LongType, NestedField, StringType

from hbp.config import DOCS, WAREHOUSE


def _catalog(warehouse: Path) -> SqlCatalog:
    warehouse.mkdir(parents=True, exist_ok=True)
    return SqlCatalog(
        "hbp",
        **{
            "uri": f"sqlite:///{warehouse / 'catalog.db'}",
            "warehouse": warehouse.resolve().as_uri(),
        },
    )


def _reset(warehouse: Path) -> SqlCatalog:
    if warehouse.exists():
        shutil.rmtree(warehouse)
    catalog = _catalog(warehouse)
    for namespace in ("bronze", "silver", "gold"):
        catalog.create_namespace(namespace)
    return catalog


def _snapshots(table) -> list[dict]:
    rows = []
    for snapshot in table.snapshots():
        summary = snapshot.summary or {}
        operation = summary.get("operation")
        rows.append(
            {
                "snapshot_id": int(snapshot.snapshot_id),
                "parent_snapshot_id": None
                if snapshot.parent_snapshot_id is None
                else int(snapshot.parent_snapshot_id),
                "operation": None if operation is None else str(operation),
                "added_records": summary.get("added-records"),
                "deleted_records": summary.get("deleted-records"),
            }
        )
    return rows


def publish(bundle: dict, warehouse: Path | None = None) -> dict:
    warehouse = warehouse or WAREHOUSE
    catalog = _reset(warehouse)
    properties = {
        "format-version": "2",
        "write.delete.mode": "merge-on-read",
        "write.update.mode": "merge-on-read",
        "write.merge.mode": "merge-on-read",
    }

    months = bundle["months_long"]
    # Keep the lakehouse demonstrable without rewriting half a million price rows
    # into a second copy of the parquet snapshot. Prices stay in the snapshot file
    # (and in the Flink job). The lakehouse holds the postcode battery months,
    # which is the table the regulator revises, plus the gold payback mart.
    battery_schema = Schema(
        NestedField(1, "postcode", StringType(), required=True),
        NestedField(2, "state", StringType(), required=True),
        NestedField(3, "install_month", DateType(), required=True),
        NestedField(4, "installs", LongType(), required=True),
    )
    battery = catalog.create_table(
        "silver.battery_month",
        schema=battery_schema,
        partition_spec=PartitionSpec(
            PartitionField(3, 1000, MonthTransform(), "install_month_part"),
        ),
        properties=properties,
    )
    arrow = pa.table(
        {
            "postcode": months.postcode.tolist(),
            "state": months.state.tolist(),
            "install_month": [value.date() for value in months.install_month],
            "installs": [int(value) for value in months.installs],
        },
        schema=pa.schema(
            [
                pa.field("postcode", pa.string(), nullable=False),
                pa.field("state", pa.string(), nullable=False),
                pa.field("install_month", pa.date32(), nullable=False),
                pa.field("installs", pa.int64(), nullable=False),
            ]
        ),
    )
    battery.append(arrow)
    append_id = battery.current_snapshot().snapshot_id

    # Schema evolution: a note column that did not exist on the first snapshot.
    with battery.update_schema() as update:
        update.add_column("revision_note", StringType())
    battery = catalog.load_table("silver.battery_month")

    # Drill a one-row correction on a real postcode-month, then restore it.
    september = months[(months.install_month == "2026-09-01") & (months.installs > 0)]
    sample = september.sort_values("installs", ascending=False).head(1)
    if sample.empty:
        sample = months[months.installs > 0].head(1)
    postcode = str(sample.iloc[0].postcode)
    month: date = sample.iloc[0].install_month.date()
    original = int(sample.iloc[0].installs)
    state = str(sample.iloc[0].state)

    battery.delete(And(EqualTo("postcode", postcode), EqualTo("install_month", month)))
    def _revision(installs: int, note: str) -> pa.Table:
        return pa.table(
            {
                "postcode": [postcode],
                "state": [state],
                "install_month": [month],
                "installs": [installs],
                "revision_note": [note],
            },
            schema=pa.schema(
                [
                    pa.field("postcode", pa.string(), nullable=False),
                    pa.field("state", pa.string(), nullable=False),
                    pa.field("install_month", pa.date32(), nullable=False),
                    pa.field("installs", pa.int64(), nullable=False),
                    pa.field("revision_note", pa.string(), nullable=True),
                ]
            ),
        )

    battery.append(_revision(original + 1, "drill: not a CER figure"))
    drilled_id = battery.current_snapshot().snapshot_id

    battery.delete(And(EqualTo("postcode", postcode), EqualTo("install_month", month)))
    battery.append(_revision(original, "restored to the CER postcode file"))
    restored_id = battery.current_snapshot().snapshot_id

    drilled = battery.scan(snapshot_id=drilled_id).to_arrow().to_pandas()
    drilled_value = int(
        drilled.loc[drilled.postcode == postcode, "installs"].iloc[0]
        if (drilled.postcode == postcode).any()
        else -1
    )
    # The drilled snapshot may contain the revised row only as the latest file for
    # that key; sum installs for the postcode-month.
    drilled_rows = drilled[(drilled.postcode == postcode)]
    drilled_rows = drilled_rows[drilled_rows.install_month.astype(str).str.startswith(str(month))]
    restored = battery.scan().to_arrow().to_pandas()
    restored_rows = restored[restored.postcode == postcode]
    restored_rows = restored_rows[restored_rows.install_month.astype(str).str.startswith(str(month))]
    restored_installs = int(restored_rows.installs.sum()) if len(restored_rows) else None
    if restored_installs != original:
        raise RuntimeError(
            f"Correction drill did not restore {postcode} {month}: {restored_installs} != {original}"
        )

    pay = bundle["payback"]
    pay_schema = Schema(
        NestedField(1, "region", StringType(), required=True),
        NestedField(2, "usable_kwh", LongType(), required=True),
        NestedField(3, "scenario", StringType(), required=True),
        NestedField(4, "annual_value_aud", DoubleType(), required=True),
        NestedField(5, "household_price_aud", DoubleType(), required=True),
        NestedField(6, "payback_years", DoubleType(), required=True),
    )
    gold = catalog.create_table(
        "gold.payback",
        schema=pay_schema,
        partition_spec=PartitionSpec(
            PartitionField(3, 1000, IdentityTransform(), "scenario"),
        ),
        properties=properties,
    )
    gold.append(
        pa.table(
            {
                "region": pay.region.tolist(),
                "usable_kwh": [int(value) for value in pay.usable_kwh],
                "scenario": pay.scenario.tolist(),
                "annual_value_aud": [float(value) for value in pay.annual_value_aud],
                "household_price_aud": [float(value) for value in pay.household_price_aud],
                "payback_years": [float(value) for value in pay.payback_years],
            },
            schema=pa.schema(
                [
                    pa.field("region", pa.string(), nullable=False),
                    pa.field("usable_kwh", pa.int64(), nullable=False),
                    pa.field("scenario", pa.string(), nullable=False),
                    pa.field("annual_value_aud", pa.float64(), nullable=False),
                    pa.field("household_price_aud", pa.float64(), nullable=False),
                    pa.field("payback_years", pa.float64(), nullable=False),
                ]
            ),
        )
    )

    # Bronze is the untouched monthly file, partitioned the same way, before the drill.
    bronze = catalog.create_table(
        "bronze.battery_month",
        schema=battery_schema,
        partition_spec=PartitionSpec(
            PartitionField(3, 1000, MonthTransform(), "install_month_part"),
        ),
        properties=properties,
    )
    bronze.append(arrow)

    report = {
        "catalog": "sqlite",
        "warehouse": str(warehouse),
        "format_version": 2,
        "delete_mode_requested": "merge-on-read",
        "delete_mode_actual": (
            "PyIceberg 0.12 rewrites the affected data file (copy-on-write) and warns "
            "that merge-on-read equality deletes are not implemented yet. "
            "Trino in docker-compose applies write.delete.mode=merge-on-read for real."
        ),
        "partitioning": {
            "silver.battery_month": "month(install_month) hidden partition",
            "gold.payback": "identity(scenario) hidden partition",
        },
        "schema_evolution": {
            "table": "silver.battery_month",
            "added_column": "revision_note",
            "snapshot_before_column": append_id,
        },
        "correction_drill": {
            "postcode": postcode,
            "install_month": str(month),
            "cer_installs": original,
            "drilled_installs": original + 1,
            "snapshot_after_append": append_id,
            "snapshot_drilled": drilled_id,
            "snapshot_restored": restored_id,
            "drilled_rows_for_postcode_month": int(drilled_rows.installs.sum()) if len(drilled_rows) else drilled_value,
            "restored_installs": restored_installs,
            "note": (
                "The drilled snapshot is a one-installation fiction used to show a row-level "
                "update. The restored snapshot matches the CER file. It is not a published statistic."
            ),
        },
        "tables": {
            "bronze.battery_month": _snapshots(bronze),
            "silver.battery_month": _snapshots(catalog.load_table("silver.battery_month")),
            "gold.payback": _snapshots(catalog.load_table("gold.payback")),
        },
    }
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "iceberg-snapshots.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
