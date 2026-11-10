"""Timings for the gold aggregation and for a one-row correction.

Run on the developer machine and again in GitHub Actions. Both cost $0.
Flink's timing is merged in when benchmarks/flink_timing.json exists, because
the streaming job is a separate process with its own Java runtime.
Trino is timed by scripts/trino_smoke.sh when the compose stack is up.
"""

from __future__ import annotations

import json
import time

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from hbp.config import BENCHMARKS, SNAPSHOT


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 2)


def _duckdb_day_agg(path: str) -> int:
    con = duckdb.connect()
    frame = con.sql(
        f"""
        SELECT region,
               CAST(ts - INTERVAL 1 SECOND AS DATE) AS nem_date,
               avg(rrp) AS avg_rrp,
               count(*) FILTER (WHERE rrp < 0) AS negative_intervals
        FROM read_parquet('{path}')
        GROUP BY 1, 2
        """
    ).to_arrow_table()
    con.close()
    return frame.num_rows


def _arrow_day_agg(path: str) -> int:
    table = pq.read_table(path, columns=["region", "ts", "rrp"])
    # Day bucket in milliseconds, matching the SQL date of (ts - 1 second).
    shifted = pc.subtract(table.column("ts"), pa.scalar(1_000_000, type=pa.duration("us")))
    day = pc.floor_temporal(shifted, unit="day")
    grouped = table.append_column("nem_date", day).group_by(["region", "nem_date"]).aggregate(
        [("rrp", "mean"), ("rrp", "count")]
    )
    return grouped.num_rows


def _correction_costs(path: str) -> dict:
    """Copy-on-write rewrites a month file. Merge-on-read writes the deleted keys only.

    The merge-on-read figure is the write-side cost. Readers still have to apply the
    delete. PyIceberg's own delete rewrites the file; Trino's merge-on-read path is
    what the compose smoke exercises.
    """
    table = pq.read_table(path, columns=["region", "ts", "rrp"]).slice(0, 9000)
    started = time.perf_counter()
    kept = table.filter(pc.not_equal(table.column("region"), "SA1"))
    sink = pa.BufferOutputStream()
    pa.parquet.write_table(kept, sink, compression="zstd")
    cow_bytes = sink.getvalue().size
    cow_ms = _ms(started)

    started = time.perf_counter()
    keys = table.filter(pc.equal(table.column("region"), "SA1")).select(["region", "ts"]).slice(0, 1)
    sink = pa.BufferOutputStream()
    pa.parquet.write_table(keys, sink, compression="zstd")
    mor_bytes = sink.getvalue().size
    mor_ms = _ms(started)
    return {
        "rows_in_file": table.num_rows,
        "copy_on_write_rewrite_ms": cow_ms,
        "copy_on_write_bytes": cow_bytes,
        "merge_on_read_key_write_ms": mor_ms,
        "merge_on_read_key_bytes": mor_bytes,
        "note": (
            "Copy-on-write rewrites the surviving rows. Merge-on-read, on the write path, "
            "stores the deleted key. PyIceberg 0.12 falls back to copy-on-write; "
            "Trino honours write.delete.mode=merge-on-read in the compose stack."
        ),
    }


def run() -> dict:
    path = str(SNAPSHOT / "aemo_price_demand_202511_202610.parquet")
    started = time.perf_counter()
    duck_rows = _duckdb_day_agg(path)
    duck_ms = _ms(started)
    started = time.perf_counter()
    arrow_rows = _arrow_day_agg(path)
    arrow_ms = _ms(started)
    result = {
        "machine": "local or GitHub-hosted runner, $0",
        "price_rows": None,
        "duckdb_day_agg_ms": duck_ms,
        "duckdb_day_groups": duck_rows,
        "pyarrow_day_agg_ms": arrow_ms,
        "pyarrow_day_groups": arrow_rows,
        "correction": _correction_costs(path),
        "flink": None,
        "trino": None,
    }
    # row count of the source, not the groups
    import duckdb

    con = duckdb.connect()
    result["price_rows"] = int(
        con.execute("SELECT count(*) FROM read_parquet(?)", [path]).fetchone()[0]
    )
    con.close()
    flink_path = BENCHMARKS / "flink_timing.json"
    if flink_path.exists():
        result["flink"] = json.loads(flink_path.read_text())
    trino_path = BENCHMARKS / "trino_timing.json"
    if trino_path.exists():
        result["trino"] = json.loads(trino_path.read_text())
    BENCHMARKS.mkdir(parents=True, exist_ok=True)
    (BENCHMARKS / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    print(json.dumps(run(), indent=2))


if __name__ == "__main__":
    main()
