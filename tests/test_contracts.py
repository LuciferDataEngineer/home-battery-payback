from pathlib import Path

import pandas as pd

from hbp.contracts import BATTERY_MONTH_SCHEMA, PRICE_SCHEMA, contract_columns, split_failures

ROOT = Path(__file__).resolve().parents[1]


def test_yaml_columns_match_pandera():
    price_yaml = contract_columns(ROOT / "data" / "contracts" / "prices.yaml")
    battery_yaml = contract_columns(ROOT / "data" / "contracts" / "battery_month.yaml")
    assert price_yaml == list(PRICE_SCHEMA.columns)
    assert battery_yaml == list(BATTERY_MONTH_SCHEMA.columns)


def test_bad_price_is_quarantined():
    frame = pd.DataFrame(
        {
            "region": ["SA1", "SA1", "MARS"],
            "ts": pd.to_datetime(["2026-01-01 00:05", "2026-01-01 00:10", "2026-01-01 00:15"]),
            "rrp": [10.0, 99_999.0, 20.0],
            "demand": [1000.0, 1000.0, 1000.0],
        }
    )
    good, bad = split_failures(frame, PRICE_SCHEMA)
    assert len(good) == 1
    assert set(bad.region) == {"SA1", "MARS"} or len(bad) == 2
    assert 99_999.0 in set(bad.rrp) or "MARS" in set(bad.region)
