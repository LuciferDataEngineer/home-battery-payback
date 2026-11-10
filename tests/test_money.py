import math

import pytest

from hbp.money import cycle_value_aud, household_price_aud, stc_count, stc_value_aud


def test_stc_taper_matches_published_examples():
    # 10 kWh at 6.8 is 68 certificates. 20 kWh is 119. Both are the worked
    # examples used by public rebate tables for the post-1 May 2026 factor.
    assert stc_count(10, 6.8) == 68
    assert stc_count(13.5, 6.8) == 91
    assert stc_count(20, 6.8) == 119
    assert stc_count(10, 5.7) == 57
    assert stc_value_aud(10, 6.8) == 2720


def test_cut_adds_the_lost_certificates_at_forty_dollars():
    current = household_price_aud(10, "current")
    cut = household_price_aud(10, "cut")
    assert current == 7384
    assert cut - current == pytest.approx(40 * (68 - 57))


def test_negative_charge_price_pays_for_the_losses():
    # Buying more energy because of losses increases the payment when the
    # charge price is negative.
    paid = cycle_value_aud(10, charge_rrp=-10, discharge_rrp=100)
    flat = 0.010 * (100 - (-10) / 0.9)
    assert paid == pytest.approx(flat)
    assert paid > 0.010 * (100 - (-10))


def test_unknown_size_is_rejected():
    with pytest.raises(KeyError):
        household_price_aud(13, "current")
    assert math.floor(119.68) == 119
