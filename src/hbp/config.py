"""Paths, market geography, and the payback assumptions.

Every dollar figure that is an assumption (not a measured price or count) is named here
and cited in INSIGHTS.md. Measured inputs are read from data/snapshot.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "data" / "snapshot"
SITE = ROOT / "site"
SITE_DATA = SITE / "data"
WAREHOUSE = ROOT / "data" / "warehouse"
QUARANTINE = ROOT / "data" / "quarantine"
OUTPUT = ROOT / "data" / "output"
LINEAGE = ROOT / "lineage"
BENCHMARKS = ROOT / "benchmarks"
DOCS = ROOT / "docs"

NEM_REGIONS = ("NSW1", "QLD1", "VIC1", "SA1", "TAS1")
STATE_TO_NEM = {
    "NSW": "NSW1",
    "ACT": "NSW1",
    "VIC": "VIC1",
    "QLD": "QLD1",
    "SA": "SA1",
    "TAS": "TAS1",
}
STATE_NAMES = {
    "NSW": "New South Wales",
    "VIC": "Victoria",
    "QLD": "Queensland",
    "SA": "South Australia",
    "WA": "Western Australia",
    "TAS": "Tasmania",
    "NT": "Northern Territory",
    "ACT": "Australian Capital Territory",
}

# NEM settlement timestamps are interval-ending, in Australian Eastern Standard Time
# all year. The market does not shift to AEDT.
PRICE_TIME_LABEL = "NEM market time (AEST, no daylight-saving shift)"

# Round-trip efficiency. Home LFP systems are commonly warranted around 90%.
# This is an assumption, not a measurement from the price files.
ROUND_TRIP_EFFICIENCY = 0.90

# One full cycle a day, using the cheapest 2 hours in the middle of the day and the
# dearest 2 hours in the evening. A 10 kWh battery needs about 5 kW for those 2 hours.
# A 20 kWh battery needs about 10 kW. Many installed systems can do that; some cannot.
CYCLES_PER_DAY = 1
CHARGE_HOURS = (12, 15)  # interval-ending hour, inclusive
DISCHARGE_HOURS = (18, 21)

# Statutory STC Clearing House price. Renewable Energy (Electricity) Act 2000.
# DCCEEW: the government buys battery STCs at this price.
STC_CLEARING_HOUSE_AUD = 40.0

# DCCEEW Table 1, Cheaper Home Batteries Program, amended STC factor.
STC_FACTOR_CURRENT = 6.8  # 1 May 2026 to 31 December 2026
STC_FACTOR_CUT = 5.7  # already legislated step-down, 1 January 2027 to 30 June 2027

# Solar Choice Battery Price Index, updated 6 November 2026.
# Battery-only national average, installation and GST included, federal rebate already deducted.
# https://www.solarchoice.net.au/solar-batteries/price/
SOLAR_CHOICE_NET_PRICE_AUD = {
    10: 7384,
    20: 14172,
}

# CER postcode file this snapshot was built from. The pipeline recomputes the total;
# this constant is the published national total used as a reconciliation check.
CER_AS_AT = "2026-09-30"
CER_PAGE_UPDATED = "2026-10-20"
PRICE_COVERAGE = "2025-11-01 to 2026-10-31"
CENSUS_NIGHT = "2021-08-10"
ACCESS_DATE = "2026-11-10"

# Published state totals from the CER HTML summary "Small generation unit - Solar batteries",
# current as at 30 September 2026. Postcode-range assignment differs slightly where a
# postcode crosses a border. The national total matches exactly.
CER_PUBLISHED_BATTERIES = {
    "ACT": 10284,
    "NSW": 187241,
    "NT": 1373,
    "QLD": 110567,
    "SA": 60459,
    "TAS": 5676,
    "VIC": 109979,
    "WA": 61210,
}
CER_PUBLISHED_NATIONAL = 546789
