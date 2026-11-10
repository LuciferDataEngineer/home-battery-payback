from hbp.analytics import build_all
from hbp.config import CER_PUBLISHED_BATTERIES


def test_snapshot_matches_the_regulator_total():
    bundle = build_all()
    states = bundle["states"].set_index("state")
    assert int(states.batteries.sum()) == 546789
    # Cross-border postcodes move a few dozen systems. None of the gaps is large.
    for state, published in CER_PUBLISHED_BATTERIES.items():
        assert abs(int(states.loc[state, "batteries"]) - published) < 150


def test_south_australia_pays_back_faster_than_tasmania():
    bundle = build_all()
    pay = bundle["payback"]
    current = pay[(pay.usable_kwh == 10) & (pay.scenario == "current")].set_index("region")
    assert current.loc["SA1", "payback_years"] < 12
    assert current.loc["TAS1", "payback_years"] > 30
    assert current.loc["SA1", "annual_value_aud"] > current.loc["NSW1", "annual_value_aud"]
    # One year of complete days, not the stub interval on 1 November.
    assert int(bundle["regions"].days.min()) == 365
    assert float(bundle["regions"].set_index("region").loc["SA1", "avg_charge"]) < 0


def test_may_drop_is_in_the_monthly_series():
    monthly = build_all()["monthly"].set_index("install_month")
    april = int(monthly.loc["2026-04-01", "installs"])
    may = int(monthly.loc["2026-05-01", "installs"])
    assert april == 87128
    assert may == 23679
    assert may < april * 0.4


def test_storage_is_about_fifteen_gigawatt_hours():
    gwh = float(build_all()["states"].gwh.sum())
    assert 15.0 < gwh < 15.6
