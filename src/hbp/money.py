"""Subsidy arithmetic and the wholesale value of one battery cycle.

These are the only places a dollar of payback is calculated. Inputs are either a
measured regional price ($/MWh) or a named assumption in config.py.
"""

from __future__ import annotations

import math

from hbp.config import (
    ROUND_TRIP_EFFICIENCY,
    SOLAR_CHOICE_NET_PRICE_AUD,
    STC_CLEARING_HOUSE_AUD,
    STC_FACTOR_CURRENT,
    STC_FACTOR_CUT,
)


def stc_count(usable_kwh: float, factor: float) -> int:
    """STCs for a battery installed under the post-1 May 2026 taper.

    The factor applies in full up to 14 kWh, at 60% from 14 to 28 kWh, and at 15%
    from 28 to 50 kWh. Nothing is paid above 50 kWh. The count is rounded down.
    """
    capped = min(max(float(usable_kwh), 0.0), 50.0)
    full = min(capped, 14.0) * factor
    mid = min(max(capped - 14.0, 0.0), 14.0) * factor * 0.60
    tail = min(max(capped - 28.0, 0.0), 22.0) * factor * 0.15
    return math.floor(full + mid + tail + 1e-9)


def stc_value_aud(usable_kwh: float, factor: float) -> float:
    return stc_count(usable_kwh, factor) * STC_CLEARING_HOUSE_AUD


def household_price_aud(usable_kwh: int, scenario: str) -> float:
    """After-rebate price the household pays.

    Current uses the Solar Choice November 2026 battery-only average, which already
    includes the federal discount. The cut scenario adds the certificates the household
    would lose if the factor stepped from 6.8 to the legislated 5.7, valued at the
    $40 clearing-house price. Installers sometimes pass through a lower spot price,
    so the cut is an upper bound on the extra dollars.
    """
    if usable_kwh not in SOLAR_CHOICE_NET_PRICE_AUD:
        raise KeyError(f"No published installed price for {usable_kwh} kWh")
    net = float(SOLAR_CHOICE_NET_PRICE_AUD[usable_kwh])
    if scenario == "current":
        return net
    if scenario != "cut":
        raise KeyError(scenario)
    lost = stc_value_aud(usable_kwh, STC_FACTOR_CURRENT) - stc_value_aud(
        usable_kwh, STC_FACTOR_CUT
    )
    return net + lost


def cycle_value_aud(usable_kwh: float, charge_rrp: float, discharge_rrp: float) -> float:
    """Dollars earned by one cycle. Negative results are floored at zero by the caller.

    RRP is $/MWh. To deliver `usable_kwh` the battery must buy usable/efficiency from
    the grid. When the charge price is negative, buying the extra losses increases the
    payment received for charging.
    """
    mwh = usable_kwh / 1000.0
    return mwh * (discharge_rrp - charge_rrp / ROUND_TRIP_EFFICIENCY)
