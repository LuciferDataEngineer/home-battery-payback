# Benchmark

All of this runs on a free GitHub-hosted runner, or on the laptop that built the snapshot. There is no warehouse bill. Cost is **$0**.

The timings below are from the authoring machine (4 vCPU). GitHub Actions will not match them to the millisecond. The ranking should. `benchmarks/results.json` is what `python -m hbp.benchmark` last wrote, including a Flink timing when `benchmarks/flink_timing.json` is present.

## Gold aggregation: one row per region per day

525,600 five-minute prices (5 NEM regions, 1 Nov 2025 to 31 Oct 2026). The query is the mean price and the count of negative prices by region and day. Both engines returned 1,825 groups.

| Engine | Time | What it is doing |
| --- | --- | --- |
| DuckDB | 51 ms | Scans the Parquet snapshot and groups in process |
| PyArrow | 171 ms | Same group, through Arrow compute |
| Flink SQL `TUMBLE` | 7.2 s | 288 rows, one region, one day. Almost all of that is the local mini-cluster starting |
| Trino | not timed here | The compose job runs the real query path. This machine has no Docker daemon, so the number is left null rather than invented |

DuckDB is the mart engine because it is the fastest of the engines that finish without a cluster, and the dashboard is a static file. Flink is here for event time, not because it wins a stopwatch on a file that already fits in memory.

## Correcting one row

Clean Energy Regulator files for the latest months keep moving as certificates are lodged. The lakehouse drill deletes one postcode-month and writes it back (see `docs/iceberg-snapshots.json`, postcode 2765, September 2026, 112 installs, drilled to 113, restored to 112).

On a 9,000-row slice of the price file, rewriting the surviving rows (copy-on-write) took 2.5 ms and 98 KB. Writing only the deleted key (the write side of merge-on-read) took 0.3 ms and 506 bytes. Readers of a merge-on-read table still have to apply that key, so the saving is on the write, which is the part that hurts when a whole month is revised.

PyIceberg 0.12 accepts `write.delete.mode=merge-on-read` and then warns that equality deletes are not implemented, and rewrites the file. The September partition rewrite in the drill is that copy-on-write path (`Operation.OVERWRITE`, 2,489 rows removed, 2,488 written back, then a one-row append). Trino in `docker compose` sets the same property and actually deletes with merge-on-read. `scripts/trino_smoke.sh` is that demonstration.

## What not to conclude

A 7 second Flink job on 288 rows does not mean Flink is slow at aggregation. It means a local mini cluster is the wrong tool for a file that DuckDB scans in 51 ms, and the right tool for a stream of late prices, which is what `tests/test_flink.py` checks.
