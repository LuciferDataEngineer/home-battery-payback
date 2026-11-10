"""Measure uptake and wholesale payback from the committed snapshot.

Nothing in this module invents a price, a count, or a dwelling. Assumptions
(efficiency, one cycle a day, installed prices, the certificate factor) live in
config.py and money.py and are labelled as assumptions in the export.
"""

from __future__ import annotations

import json
from functools import lru_cache

import duckdb
import pandas as pd

from hbp.config import (
    CER_PUBLISHED_BATTERIES,
    CER_PUBLISHED_NATIONAL,
    NEM_REGIONS,
    PRICE_COVERAGE,
    ROUND_TRIP_EFFICIENCY,
    SNAPSHOT,
    SOLAR_CHOICE_NET_PRICE_AUD,
    STATE_NAMES,
    STATE_TO_NEM,
    STC_FACTOR_CURRENT,
    STC_FACTOR_CUT,
)
from hbp.geo import normalise_postcode, state_of_postcode
from hbp.money import cycle_value_aud, household_price_aud, stc_count, stc_value_aud

MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def manifest() -> dict:
    return json.loads((SNAPSHOT / "MANIFEST.json").read_text())


def verify_snapshot() -> dict:
    """Reject a snapshot whose bytes no longer match the manifest."""
    import hashlib

    document = manifest()
    for item in document["files"]:
        path = SNAPSHOT / item["file"]
        if not path.exists():
            raise FileNotFoundError(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise ValueError(f"sha256 mismatch for {item['file']}")
    return document


def _parse_month_label(label: str) -> pd.Timestamp:
    # "Jul 2025 - Installation Quantity" or "Jul 2025 - Usable capacity in kWh"
    head = label.split(" - ")[0].strip()
    month_name, year = head.split()
    return pd.Timestamp(year=int(year), month=MONTHS[month_name], day=1)


def _number(value: object) -> float:
    text = str(value).strip().replace(",", "")
    if text in {"", "nan", "None"}:
        return 0.0
    return float(text)


def load_battery_months() -> pd.DataFrame:
    frame = pd.read_csv(SNAPSHOT / "cer_battery_installations.csv", dtype=str)
    postcode_col = frame.columns[0]
    month_cols = [col for col in frame.columns[1:] if not col.lower().startswith("total")]
    rows: list[dict] = []
    for record in frame.to_dict(orient="records"):
        postcode = normalise_postcode(record[postcode_col])
        if postcode is None or postcode == "0000":
            continue
        state = state_of_postcode(postcode)
        if state is None:
            continue
        for column in month_cols:
            installs = int(round(_number(record[column])))
            rows.append(
                {
                    "postcode": postcode,
                    "state": state,
                    "install_month": _parse_month_label(column),
                    "installs": installs,
                }
            )
    out = pd.DataFrame(rows)
    out["install_month"] = pd.to_datetime(out["install_month"])
    return out


def load_battery_capacity() -> pd.DataFrame:
    frame = pd.read_csv(SNAPSHOT / "cer_battery_capacity.csv", dtype=str)
    postcode_col = frame.columns[0]
    total_col = frame.columns[-1]
    rows = []
    for record in frame.to_dict(orient="records"):
        postcode = normalise_postcode(record[postcode_col])
        if postcode is None or postcode == "0000":
            continue
        state = state_of_postcode(postcode)
        if state is None:
            continue
        rows.append(
            {
                "postcode": postcode,
                "state": state,
                "usable_kwh": _number(record[total_col]),
            }
        )
    return pd.DataFrame(rows)


def load_solar_totals() -> pd.DataFrame:
    frame = pd.read_csv(SNAPSHOT / "cer_solar_installations.csv", dtype=str)
    postcode_col = frame.columns[0]
    total_col = "Total Installation Quantity"
    rows = []
    for record in frame.to_dict(orient="records"):
        postcode = normalise_postcode(record[postcode_col])
        if postcode is None or postcode == "0000":
            continue
        state = state_of_postcode(postcode)
        if state is None:
            continue
        rows.append(
            {
                "postcode": postcode,
                "state": state,
                "solar_systems": int(round(_number(record[total_col]))),
            }
        )
    return pd.DataFrame(rows)


def load_dwellings() -> pd.DataFrame:
    frame = pd.read_csv(SNAPSHOT / "abs_poa_occupied_dwellings_2021.csv", dtype=str)
    rows = []
    for record in frame.to_dict(orient="records"):
        postcode = normalise_postcode(record["postcode"])
        if postcode is None:
            continue
        state = state_of_postcode(postcode)
        if state is None:
            continue
        rows.append(
            {
                "postcode": postcode,
                "state": state,
                "occupied_private_dwellings": int(_number(record["occupied_private_dwellings"])),
            }
        )
    return pd.DataFrame(rows)


def daily_spreads() -> pd.DataFrame:
    """Best 2-hour midday charge price and best 2-hour evening discharge price.

    The window is 24 consecutive 5-minute prices. Charge windows are those that end
    between 12:00 and 15:00 NEM time. Discharge windows end between 18:00 and 21:00.
    The date of an interval is the date of its start, so the midnight interval belongs
    to the previous day.
    """
    path = (SNAPSHOT / "aemo_price_demand_202511_202610.parquet").as_posix()
    con = duckdb.connect()
    frame = con.execute(
        """
        WITH p AS (
          SELECT region,
                 ts AS interval_end,
                 CAST(ts - INTERVAL 1 SECOND AS DATE) AS nem_date,
                 rrp
          FROM read_parquet(?)
        ),
        w AS (
          SELECT region, nem_date, interval_end, rrp,
                 avg(rrp) OVER (
                   PARTITION BY region, nem_date
                   ORDER BY interval_end
                   ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
                 ) AS avg_2h,
                 count(*) OVER (
                   PARTITION BY region, nem_date
                   ORDER BY interval_end
                   ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
                 ) AS n_2h
          FROM p
        ),
        charge AS (
          SELECT region, nem_date, interval_end AS charge_end, avg_2h AS charge_rrp
          FROM w
          WHERE n_2h = 24 AND hour(interval_end) BETWEEN 12 AND 15
          QUALIFY row_number() OVER (
            PARTITION BY region, nem_date ORDER BY avg_2h, interval_end
          ) = 1
        ),
        discharge AS (
          SELECT region, nem_date, interval_end AS discharge_end, avg_2h AS discharge_rrp
          FROM w
          WHERE n_2h = 24 AND hour(interval_end) BETWEEN 18 AND 21
          QUALIFY row_number() OVER (
            PARTITION BY region, nem_date ORDER BY avg_2h DESC, interval_end
          ) = 1
        ),
        stats AS (
          SELECT region, nem_date,
                 min(rrp) AS trough_rrp,
                 max(rrp) AS peak_rrp,
                 count(*) FILTER (WHERE rrp < 0) AS negative_intervals,
                 count(*) AS intervals
          FROM w
          GROUP BY 1, 2
        )
        SELECT s.region, s.nem_date, c.charge_end, c.charge_rrp,
               d.discharge_end, d.discharge_rrp,
               d.discharge_rrp - c.charge_rrp AS spread_rrp,
               s.trough_rrp, s.peak_rrp, s.negative_intervals, s.intervals
        FROM stats s
        JOIN charge c USING (region, nem_date)
        JOIN discharge d USING (region, nem_date)
        WHERE s.intervals >= 280
        ORDER BY 1, 2
        """,
        [path],
    ).fetchdf()
    con.close()
    return frame


def hourly_profile() -> pd.DataFrame:
    path = (SNAPSHOT / "aemo_price_demand_202511_202610.parquet").as_posix()
    con = duckdb.connect()
    frame = con.execute(
        """
        SELECT region,
               hour(ts) AS hour_ending,
               avg(rrp) AS avg_rrp,
               count(*) FILTER (WHERE rrp < 0) AS negative_intervals,
               count(*) AS intervals
        FROM read_parquet(?)
        GROUP BY 1, 2
        ORDER BY 1, 2
        """,
        [path],
    ).fetchdf()
    con.close()
    return frame


def price_quality() -> dict:
    path = (SNAPSHOT / "aemo_price_demand_202511_202610.parquet").as_posix()
    con = duckdb.connect()
    row = con.execute(
        """
        SELECT count(*) AS rows,
               count(*) FILTER (
                 WHERE region NOT IN ('NSW1','QLD1','VIC1','SA1','TAS1')
                    OR rrp IS NULL OR rrp < -1000.01 OR rrp > 25000
                    OR demand IS NULL OR demand < -5000 OR demand > 20000
               ) AS failing,
               min(rrp) AS min_rrp,
               max(rrp) AS max_rrp,
               count(DISTINCT region) AS regions
        FROM read_parquet(?)
        """,
        [path],
    ).fetchone()
    con.close()
    failing = int(row[1])
    if failing:
        raise ValueError(f"{failing} price rows failed the contract")
    return {
        "rows": int(row[0]),
        "failing": failing,
        "min_rrp": float(row[2]),
        "max_rrp": float(row[3]),
        "regions": int(row[4]),
    }


def region_summary(daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for region, part in daily.groupby("region"):
        value_10 = part.apply(
            lambda row: max(cycle_value_aud(10, row.charge_rrp, row.discharge_rrp), 0.0),
            axis=1,
        )
        rows.append(
            {
                "region": region,
                "days": int(len(part)),
                "avg_spread": float(part.spread_rrp.mean()),
                "median_spread": float(part.spread_rrp.median()),
                "avg_charge": float(part.charge_rrp.mean()),
                "avg_discharge": float(part.discharge_rrp.mean()),
                "avg_trough": float(part.trough_rrp.mean()),
                "avg_peak": float(part.peak_rrp.mean()),
                "negative_intervals": int(part.negative_intervals.sum()),
                "intervals": int(part.intervals.sum()),
                "annual_value_10kwh": float(value_10.sum()),
                "days_paid_to_charge": int((part.charge_rrp < 0).sum()),
            }
        )
    out = pd.DataFrame(rows)
    out["negative_pct"] = 100.0 * out.negative_intervals / out.intervals
    return out.sort_values("avg_spread", ascending=False).reset_index(drop=True)


def payback_table(regions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    factors = {"current": STC_FACTOR_CURRENT, "cut": STC_FACTOR_CUT}
    for region_row in regions.itertuples(index=False):
        for kwh in SOLAR_CHOICE_NET_PRICE_AUD:
            annual_10 = float(region_row.annual_value_10kwh)
            annual = annual_10 * (kwh / 10.0)
            for scenario, factor in factors.items():
                cost = household_price_aud(kwh, scenario)
                years = cost / annual if annual > 0 else None
                rows.append(
                    {
                        "region": region_row.region,
                        "usable_kwh": kwh,
                        "scenario": scenario,
                        "stc_factor": factor,
                        "stc_count": stc_count(kwh, factor),
                        "stc_value_aud": stc_value_aud(kwh, factor),
                        "household_price_aud": cost,
                        "annual_value_aud": annual,
                        "payback_years": years,
                        "round_trip_efficiency": ROUND_TRIP_EFFICIENCY,
                    }
                )
    return pd.DataFrame(rows)


def uptake_frames() -> dict[str, pd.DataFrame]:
    months = load_battery_months()
    capacity = load_battery_capacity()
    solar = load_solar_totals()
    dwellings = load_dwellings()

    installs = months.groupby(["postcode", "state"], as_index=False)["installs"].sum()
    installs = installs.rename(columns={"installs": "batteries"})
    published_total = int(installs.batteries.sum())
    if published_total != CER_PUBLISHED_NATIONAL:
        raise ValueError(
            f"Postcode batteries sum to {published_total}, "
            f"CER published national total is {CER_PUBLISHED_NATIONAL}"
        )

    by_state_b = installs.groupby("state", as_index=False)["batteries"].sum()
    by_state_k = capacity.groupby("state", as_index=False)["usable_kwh"].sum()
    by_state_s = solar.groupby("state", as_index=False)["solar_systems"].sum()
    by_state_d = dwellings.groupby("state", as_index=False)["occupied_private_dwellings"].sum()
    states = by_state_b.merge(by_state_k, on="state").merge(by_state_s, on="state").merge(
        by_state_d, on="state"
    )
    # Dwellings only exist for postcodes in the 2021 postal areas. A few dozen
    # batteries sit in postcodes the census file does not list; keep them in the
    # battery total and out of the per-1,000 rate.
    matched = installs.merge(dwellings[["postcode"]], on="postcode", how="inner")
    rate_batteries = matched.groupby("state")["batteries"].sum()
    states["batteries_with_dwelling"] = states["state"].map(rate_batteries).fillna(0).astype(int)
    states["per_1000_dwellings"] = (
        1000.0 * states.batteries_with_dwelling / states.occupied_private_dwellings
    )
    states["per_1000_solar"] = 1000.0 * states.batteries / states.solar_systems
    states["gwh"] = states.usable_kwh / 1_000_000.0
    states["name"] = states["state"].map(STATE_NAMES)
    states["nem_region"] = states["state"].map(STATE_TO_NEM)
    states["in_nem"] = states["nem_region"].notna()
    states["published_batteries"] = states["state"].map(CER_PUBLISHED_BATTERIES)
    states["published_gap"] = states.batteries - states.published_batteries

    monthly = months.groupby("install_month", as_index=False)["installs"].sum()
    monthly["provisional"] = monthly.install_month >= pd.Timestamp("2026-07-01")

    post = installs.merge(dwellings, on=["postcode", "state"], how="left")
    post = post.merge(solar, on=["postcode", "state"], how="left")
    post["occupied_private_dwellings"] = post.occupied_private_dwellings.fillna(0).astype(int)
    post["solar_systems"] = post.solar_systems.fillna(0).astype(int)
    post["per_1000_dwellings"] = post.apply(
        lambda row: 1000.0 * row.batteries / row.occupied_private_dwellings
        if row.occupied_private_dwellings
        else None,
        axis=1,
    )
    post["per_1000_solar"] = post.apply(
        lambda row: 1000.0 * row.batteries / row.solar_systems if row.solar_systems else None,
        axis=1,
    )

    return {
        "months_long": months,
        "states": states,
        "monthly": monthly,
        "postcodes": post,
        "capacity": capacity,
    }


@lru_cache(maxsize=1)
def build_all() -> dict:
    verify_snapshot()
    quality = price_quality()
    daily = daily_spreads()
    if set(daily.region.unique()) != set(NEM_REGIONS):
        raise ValueError(f"Expected regions {NEM_REGIONS}, got {sorted(daily.region.unique())}")
    regions = region_summary(daily)
    payback = payback_table(regions)
    uptake = uptake_frames()
    hourly = hourly_profile()
    return {
        "quality": quality,
        "coverage": PRICE_COVERAGE,
        "daily": daily,
        "regions": regions,
        "payback": payback,
        "hourly": hourly,
        **uptake,
    }
