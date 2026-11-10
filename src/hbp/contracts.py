"""Data contracts.

Pandera checks dataframes and splits failing rows into a quarantine frame.
The full price file is also checked in SQL so a bad interval does not have to be
loaded twice. The YAML files under data/contracts/ are the human-readable copy of
the same rules; tests assert the two stay in step.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pandera.pandas as pa
import yaml
from pandera.errors import SchemaErrors

from hbp.config import NEM_REGIONS, QUARANTINE

PRICE_SCHEMA = pa.DataFrameSchema(
    {
        "region": pa.Column(str, pa.Check.isin(list(NEM_REGIONS))),
        "ts": pa.Column("datetime64[ns]", nullable=False),
        "rrp": pa.Column(float, pa.Check.in_range(-1000.01, 25000.0)),
        "demand": pa.Column(float, pa.Check.in_range(-5000.0, 20000.0)),
    },
    strict=False,
    coerce=True,
)

BATTERY_MONTH_SCHEMA = pa.DataFrameSchema(
    {
        "postcode": pa.Column(str, pa.Check.str_matches(r"^\d{4}$")),
        "state": pa.Column(str, pa.Check.isin(["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"])),
        "install_month": pa.Column("datetime64[ns]", nullable=False),
        "installs": pa.Column(int, pa.Check.ge(0)),
    },
    strict=False,
    coerce=True,
)


def split_failures(frame: pd.DataFrame, schema: pa.DataFrameSchema) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (kept, quarantined). An empty quarantine frame keeps the same columns."""
    try:
        schema.validate(frame, lazy=True)
        return frame, frame.iloc[0:0].copy()
    except SchemaErrors as exc:
        indexes = exc.failure_cases["index"].dropna()
        bad_index = set(int(i) for i in indexes.tolist())
        bad = frame.loc[frame.index.isin(bad_index)].copy()
        good = frame.loc[~frame.index.isin(bad_index)].copy()
        return good, bad


def write_quarantine(name: str, frame: pd.DataFrame) -> Path | None:
    if frame.empty:
        return None
    QUARANTINE.mkdir(parents=True, exist_ok=True)
    path = QUARANTINE / f"{name}.csv"
    frame.to_csv(path, index=False)
    return path


def contract_columns(path: Path) -> list[str]:
    document = yaml.safe_load(path.read_text())
    return [column["name"] for column in document["columns"]]
