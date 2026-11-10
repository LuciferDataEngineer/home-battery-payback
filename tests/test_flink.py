"""Event-time windows. Skipped unless PyFlink is installed.

The fixture is arrival order, not event-time order. A 5-minute allowed lateness
keeps a row that is four minutes behind the newest event and drops a row that
arrives after the watermark has moved further on.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.flink

ROOT = Path(__file__).resolve().parents[1]


def _require():
    if os.environ.get("JAVA_HOME", "") == "" and not Path("/usr/lib/jvm/java-17-openjdk-amd64").exists():
        pytest.skip("Java 17 is required")
    os.environ.setdefault("JAVA_HOME", "/usr/lib/jvm/java-17-openjdk-amd64")
    pytest.importorskip("pyflink")


def test_allowed_lateness_keeps_a_near_late_row_and_drops_an_older_one():
    _require()
    from hbp.flink_job import tumble_sums

    minute = 60_000
    # Arrival order. The 6-minute price is 4 minutes behind the 10-minute price,
    # inside a 5-minute lag. The 1-minute price arrives after a 15-minute event
    # and is outside that lag.
    events = [
        (0, 10, "SA1"),
        (10 * minute, 100, "SA1"),
        (6 * minute, 4, "SA1"),
        (15 * minute, 8, "SA1"),
        (1 * minute, 1000, "SA1"),
    ]
    rows = {start: (total, count) for start, total, count in tumble_sums(events, lag_ms=5 * minute)}
    assert rows["1970-01-01 00:00:00.000"] == (14, 2)
    assert rows["1970-01-01 00:10:00.000"] == (108, 2)
    assert all(total != 1000 for total, _count in rows.values())


def test_hop_average_matches_rows_inside_each_window():
    _require()
    from hbp.flink_job import hop_averages

    minute = 60_000
    values = [10, 20, 30, 40, 50, 60, 70, 80]
    events = [(i * 30 * minute, value, "NSW1") for i, value in enumerate(values)]
    windows = hop_averages(events, lag_ms=1)
    assert len(windows) > 1

    def parse(text: str) -> int:
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)

    for start, end, avg_rrp, count in windows:
        start_ms, end_ms = parse(start), parse(end)
        inside = [value for ts, value, _region in events if start_ms <= ts < end_ms]
        assert count == len(inside)
        assert avg_rrp == pytest.approx(sum(inside) / len(inside))


def test_one_real_day_matches_a_direct_min_and_max():
    _require()
    dataset = pytest.importorskip("pyarrow.dataset")
    from hbp.flink_job import daily_extrema

    path = ROOT / "data" / "snapshot" / "aemo_price_demand_202511_202610.parquet"
    table = dataset.dataset(path).to_table(
        filter=(
            (dataset.field("region") == "SA1")
            & (dataset.field("ts") >= datetime(2026, 1, 15))
            & (dataset.field("ts") < datetime(2026, 1, 16))
        ),
        columns=["region", "ts", "rrp"],
    )
    records = table.to_pylist()
    assert len(records) > 200
    rows = [(int(record["ts"].timestamp() * 1000), float(record["rrp"]), "SA1") for record in records]
    result = daily_extrema(rows)
    assert len(result) == 1
    _region, _start, trough, peak, count, negatives = result[0]
    prices = [record["rrp"] for record in records]
    assert count == len(records)
    assert trough == pytest.approx(min(prices), abs=0.02)
    assert peak == pytest.approx(max(prices), abs=0.02)
    assert negatives == sum(price < 0 for price in prices)
