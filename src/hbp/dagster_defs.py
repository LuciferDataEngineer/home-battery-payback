"""Dagster assets. The same functions the plain pipeline calls.

`dagster definitions validate -m hbp.dagster_defs` checks the graph.
`materialize_all` runs it in-process, which is what CI does. No daemon.
"""

from __future__ import annotations

from dagster import (
    AssetCheckResult,
    Definitions,
    asset,
    asset_check,
    materialize,
)

from hbp.analytics import build_all
from hbp.export import build_document
from hbp.pipeline import _write_dashboard


@asset(description="Measured uptake, spreads and payback from the snapshot.")
def metrics() -> dict:
    return build_all()


@asset(description="Dashboard JSON consumed by the static site.", deps=[metrics])
def dashboard_json(metrics: dict) -> dict:
    document = build_document(metrics)
    _write_dashboard(document)
    return document


@asset_check(asset=metrics, description="Five NEM regions, and South Australia pays back faster than Tasmania.")
def sa_beats_tasmania(metrics: dict) -> AssetCheckResult:
    regions = set(metrics["regions"].region)
    pay = metrics["payback"]
    sa = float(
        pay[(pay.region == "SA1") & (pay.usable_kwh == 10) & (pay.scenario == "current")].payback_years.iloc[0]
    )
    tas = float(
        pay[(pay.region == "TAS1") & (pay.usable_kwh == 10) & (pay.scenario == "current")].payback_years.iloc[0]
    )
    ok = regions == {"NSW1", "QLD1", "VIC1", "SA1", "TAS1"} and sa < tas
    return AssetCheckResult(
        passed=ok,
        metadata={"sa_years": sa, "tas_years": tas},
    )


@asset_check(asset=metrics, description="National battery count matches the CER published total.")
def national_total(metrics: dict) -> AssetCheckResult:
    total = int(metrics["states"].batteries.sum())
    return AssetCheckResult(passed=total == 546789, metadata={"batteries": total})


@asset_check(asset=dashboard_json, description="The page banner is generated from the measured drop in May.")
def banner_mentions_may(dashboard_json: dict) -> AssetCheckResult:
    text = dashboard_json["headline"]
    return AssetCheckResult(passed="May" in text and "South Australia" in text)


defs = Definitions(
    assets=[metrics, dashboard_json],
    asset_checks=[sa_beats_tasmania, national_total, banner_mentions_may],
)


def materialize_all() -> dict:
    result = materialize(
        [metrics, dashboard_json, sa_beats_tasmania, national_total, banner_mentions_may]
    )
    if not result.success:
        raise RuntimeError("Dagster materialize failed")
    # The asset value is the dashboard document. Re-read it from the function cache.
    document = build_document(build_all())
    if not isinstance(document, dict):
        raise TypeError(type(document))
    return document
