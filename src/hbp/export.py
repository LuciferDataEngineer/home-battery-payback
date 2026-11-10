"""Turn measured tables into the JSON the static dashboard reads.

Sentences are built from those tables. If a number changes when the snapshot is
refreshed, the sentence changes with it.
"""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from hbp.analytics import build_all
from hbp.config import (
    ACCESS_DATE,
    CENSUS_NIGHT,
    CER_AS_AT,
    CER_PAGE_UPDATED,
    PRICE_TIME_LABEL,
    ROUND_TRIP_EFFICIENCY,
    SITE_DATA,
    SOLAR_CHOICE_NET_PRICE_AUD,
    STC_CLEARING_HOUSE_AUD,
    STC_FACTOR_CURRENT,
    STC_FACTOR_CUT,
)

MELBOURNE = ZoneInfo("Australia/Melbourne")


def _round(value: float, digits: int = 1) -> float:
    return round(float(value), digits)


def _pay(frame: pd.DataFrame, region: str, kwh: int, scenario: str) -> pd.Series:
    match = frame[
        (frame.region == region) & (frame.usable_kwh == kwh) & (frame.scenario == scenario)
    ]
    return match.iloc[0]


def _month_label(stamp: pd.Timestamp) -> str:
    return stamp.strftime("%b %Y")


def build_document(bundle: dict | None = None) -> dict:
    bundle = bundle or build_all()
    states = bundle["states"].sort_values("per_1000_dwellings", ascending=False)
    regions = bundle["regions"]
    pay = bundle["payback"]
    monthly = bundle["monthly"].sort_values("install_month")
    sa = _pay(pay, "SA1", 10, "current")
    sa_cut = _pay(pay, "SA1", 10, "cut")
    tas = _pay(pay, "TAS1", 10, "current")
    tas_cut = _pay(pay, "TAS1", 10, "cut")
    nsw = _pay(pay, "NSW1", 10, "current")

    april = monthly.loc[monthly.install_month == "2026-04-01", "installs"]
    may = monthly.loc[monthly.install_month == "2026-05-01", "installs"]
    april_n = int(april.iloc[0])
    may_n = int(may.iloc[0])
    drop_pct = 100.0 * (april_n - may_n) / april_n

    sa_state = states.loc[states.state == "SA"].iloc[0]
    tas_state = states.loc[states.state == "TAS"].iloc[0]
    nt_state = states.loc[states.state == "NT"].iloc[0]
    batteries = int(states.batteries.sum())
    gwh = float(states.gwh.sum())
    dwellings = int(states.occupied_private_dwellings.sum())
    per_1000 = 1000.0 * int(states.batteries_with_dwelling.sum()) / dwellings

    sa_region = regions.loc[regions.region == "SA1"].iloc[0]
    tas_region = regions.loc[regions.region == "TAS1"].iloc[0]

    headline = (
        f"Validated home batteries fell from {april_n:,} in April 2026 to {may_n:,} in May, "
        f"the month the federal discount was cut back above 14 kWh. "
        f"Using only wholesale price swings, a 10 kWh battery takes about "
        f"{sa.payback_years:.0f} years to pay for itself in South Australia and about "
        f"{tas.payback_years:.0f} years in Tasmania."
    )

    post = bundle["postcodes"]
    high_solar = (
        post[post.solar_systems >= 5000]
        .sort_values("per_1000_solar", ascending=False)
        .head(8)
    )
    low_rate = (
        post[(post.occupied_private_dwellings >= 8000) & (post.solar_systems >= 3000)]
        .sort_values("per_1000_dwellings", ascending=True)
        .head(8)
    )

    def post_rows(frame: pd.DataFrame) -> list[dict]:
        rows = []
        for row in frame.itertuples(index=False):
            rows.append(
                {
                    "postcode": row.postcode,
                    "state": row.state,
                    "batteries": int(row.batteries),
                    "dwellings": int(row.occupied_private_dwellings),
                    "solar": int(row.solar_systems),
                    "per_1000_dwellings": _round(row.per_1000_dwellings)
                    if pd.notna(row.per_1000_dwellings)
                    else None,
                    "per_1000_solar": _round(row.per_1000_solar)
                    if pd.notna(row.per_1000_solar)
                    else None,
                }
            )
        return rows

    state_rows = []
    for row in states.itertuples(index=False):
        state_rows.append(
            {
                "code": row.state,
                "name": row.name,
                "batteries": int(row.batteries),
                "dwellings": int(row.occupied_private_dwellings),
                "per_1000": _round(row.per_1000_dwellings),
                "solar": int(row.solar_systems),
                "per_1000_solar": _round(row.per_1000_solar),
                "gwh": _round(row.gwh, 2),
                "nem_region": None if pd.isna(row.nem_region) else row.nem_region,
                "in_nem": bool(row.in_nem),
                "published_gap": int(row.published_gap),
            }
        )

    region_rows = []
    for row in regions.itertuples(index=False):
        region_rows.append(
            {
                "region": row.region,
                "days": int(row.days),
                "avg_spread": _round(row.avg_spread, 1),
                "avg_charge": _round(row.avg_charge, 1),
                "avg_discharge": _round(row.avg_discharge, 1),
                "negative_pct": _round(row.negative_pct, 1),
                "negative_intervals": int(row.negative_intervals),
                "annual_value_10kwh": _round(row.annual_value_10kwh, 0),
                "days_paid_to_charge": int(row.days_paid_to_charge),
            }
        )

    pay_rows = []
    for row in pay.itertuples(index=False):
        pay_rows.append(
            {
                "region": row.region,
                "usable_kwh": int(row.usable_kwh),
                "scenario": row.scenario,
                "household_price_aud": round(float(row.household_price_aud)),
                "annual_value_aud": round(float(row.annual_value_aud)),
                "payback_years": _round(row.payback_years, 1),
                "stc_count": int(row.stc_count),
                "stc_value_aud": round(float(row.stc_value_aud)),
            }
        )

    hourly_rows = []
    for row in bundle["hourly"].itertuples(index=False):
        hourly_rows.append(
            {
                "region": row.region,
                "hour_ending": int(row.hour_ending),
                "avg_rrp": _round(row.avg_rrp, 1),
            }
        )

    month_rows = []
    for row in monthly.itertuples(index=False):
        month_rows.append(
            {
                "month": row.install_month.strftime("%Y-%m"),
                "label": _month_label(row.install_month),
                "installs": int(row.installs),
                "provisional": bool(row.provisional),
            }
        )

    document = {
        "as_of_label": datetime.now(MELBOURNE).strftime("%-d %B %Y, %H:%M %Z"),
        "headline": headline,
        "kpis": [
            {
                "value": f"{batteries:,}",
                "label": "Validated home batteries",
                "detail": f"Certificates approved from 1 July 2025 to {CER_AS_AT[8:10]} Sep 2026. Later installs are still being lodged.",
                "status": "green",
            },
            {
                "value": f"{gwh:.1f} GWh",
                "label": "Usable storage on those batteries",
                "detail": f"About {gwh * 1_000_000 / batteries:.0f} kWh of usable storage each, on average.",
                "status": "green",
            },
            {
                "value": f"{sa_state.per_1000_dwellings:.0f} vs {nt_state.per_1000_dwellings:.0f}",
                "label": "Batteries per 1,000 homes, SA and the NT",
                "detail": "Homes are occupied private dwellings from the 2021 Census, so new estates look fuller than they are.",
                "status": "amber",
            },
            {
                "value": f"${sa.annual_value_aud:,.0f}",
                "label": "Wholesale earnings, 10 kWh in South Australia",
                "detail": f"Over {int(sa_region.days)} days. The same battery earned ${tas.annual_value_aud:,.0f} in Tasmania.",
                "status": "amber",
            },
            {
                "value": f"{drop_pct:.0f}%",
                "label": "Fewer batteries in May 2026 than in April",
                "detail": "The fuller discount ended on 1 May 2026. September is still incomplete, so it is not in this comparison.",
                "status": "red",
            },
        ],
        "months": month_rows,
        "states": state_rows,
        "regions": region_rows,
        "payback": pay_rows,
        "hourly": hourly_rows,
        "postcodes_by_solar": post_rows(high_solar),
        "postcodes_low_uptake": post_rows(low_rate),
        "national": {
            "batteries": batteries,
            "gwh": _round(gwh, 2),
            "dwellings": dwellings,
            "per_1000": _round(per_1000, 1),
            "april": april_n,
            "may": may_n,
            "drop_pct": _round(drop_pct, 1),
        },
        "callouts": {
            "sa_years": _round(sa.payback_years, 1),
            "sa_years_cut": _round(sa_cut.payback_years, 1),
            "tas_years": _round(tas.payback_years, 1),
            "tas_years_cut": _round(tas_cut.payback_years, 1),
            "nsw_years": _round(nsw.payback_years, 1),
            "sa_spread": _round(sa_region.avg_spread, 0),
            "tas_spread": _round(tas_region.avg_spread, 0),
            "sa_charge": _round(sa_region.avg_charge, 0),
            "sa_per_1000": _round(sa_state.per_1000_dwellings, 1),
            "tas_per_1000": _round(tas_state.per_1000_dwellings, 1),
            "extra_years_sa": _round(sa_cut.payback_years - sa.payback_years, 1),
            "price_gap_10kwh": round(float(sa_cut.household_price_aud - sa.household_price_aud)),
        },
        "assumptions": {
            "sizes_kwh": list(SOLAR_CHOICE_NET_PRICE_AUD),
            "net_price_aud": {str(k): v for k, v in SOLAR_CHOICE_NET_PRICE_AUD.items()},
            "round_trip_efficiency": ROUND_TRIP_EFFICIENCY,
            "stc_price_aud": STC_CLEARING_HOUSE_AUD,
            "factor_current": STC_FACTOR_CURRENT,
            "factor_cut": STC_FACTOR_CUT,
            "time_label": PRICE_TIME_LABEL,
        },
        "means": {
            "overview": (
                "The rebate did what rebates do: people brought installations forward. "
                "April 2026 was the last full month of the richer discount, and May was much quieter. "
                "The national count here is certificates already approved, not the higher figure ministers quoted in November, which includes batteries still waiting to be processed."
            ),
            "where": (
                "South Australia has the most batteries for the number of homes counted in 2021. "
                "Tasmania and the Northern Territory have the fewest. "
                "New South Wales has the largest number of batteries, because it has the most homes, not because uptake is the most intense. "
                "Western Australia and the Northern Territory are not in the east-coast wholesale market, so this page does not price a battery there."
            ),
            "payback": (
                "These years count only the money from charging when wholesale power is cheap and discharging when it is expensive. "
                "They do not count storing a household's own rooftop solar, which is often the larger saving, or any network payment. "
                "On that wholesale-only view, South Australia is the only region close to a 10-year warranty. "
                f"The next scheduled cut in the discount, from January 2027, adds about {sa_cut.payback_years - sa.payback_years:.1f} years in South Australia. It does not change which region pays back fastest."
            ),
            "prices": (
                f"In South Australia the cheapest two midday hours averaged about ${sa_region.avg_charge:.0f} per megawatt-hour over the year, so a battery was often paid to charge. "
                f"About {sa_region.negative_pct:.0f}% of South Australian intervals had a negative price, against {tas_region.negative_pct:.0f}% in Tasmania. "
                "That gap, not the number of batteries, is why a South Australian battery earns more from price swings."
            ),
            "action": (
                "A household should not buy a battery on wholesale swings alone unless they are in South Australia and happy with a payback near the warranty. "
                "Ask the installer for the price after the federal discount, and treat quotes that assume two full cycles every day as optimistic. "
                "A retailer with customers in South Australia or Victoria is sitting on the most negative midday prices. "
                "A government cutting the discount further will slow installations, as May 2026 already showed, and will lengthen wholesale payback most where the price swings are smallest."
            ),
        },
        "sources": [
            {
                "name": "Clean Energy Regulator, small-scale installation postcode data",
                "licence": "CC BY 4.0",
                "as_at": f"30 September 2026 (page updated {CER_PAGE_UPDATED[8:10]} October 2026)",
            },
            {
                "name": "AEMO aggregated price and demand",
                "licence": "Reuse allowed with attribution to AEMO",
                "as_at": "1 November 2025 to 31 October 2026, " + PRICE_TIME_LABEL,
            },
            {
                "name": "ABS Census 2021, General Community Profile table G34, postal areas",
                "licence": "CC BY 4.0",
                "as_at": f"Census night {CENSUS_NIGHT[8:10]} August 2021",
            },
            {
                "name": "Solar Choice Battery Price Index",
                "licence": "Published prices, cited as the cost assumption",
                "as_at": "6 November 2026",
            },
            {
                "name": "DCCEEW Cheaper Home Batteries Program, STC factor table",
                "licence": "Australian Government public information",
                "as_at": "Factor 6.8 until 31 December 2026, then 5.7",
            },
        ],
        "access_date": ACCESS_DATE,
    }
    return document


def main() -> None:
    document = build_document()
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    path = SITE_DATA / "dashboard.json"
    path.write_text(json.dumps(document, indent=2) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
